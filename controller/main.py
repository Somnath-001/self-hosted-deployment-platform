from fastapi import FastAPI, Request
import json
import docker
import time
import requests
import threading

app = FastAPI(title="Deployment Controller")

docker_client = docker.from_env()

def reconciliation_loop():
    while True:
        try:
            with open("desired_state.json", "r") as file:
                desired_state = json.load(file)

            desired_application = desired_state["application"]
            desired_image = desired_state["image"]

            containers = docker_client.containers.list()

            actual_image = None

            for container in containers:
                if container.name == desired_application:
                    image_tags = container.image.tags

                    if image_tags:
                        actual_image = image_tags[0]

            if actual_image != desired_image:
                print(
                    f"Reconciliation: desired={desired_image}, "
                    f"actual={actual_image}"
                )

                deploy_container(
                    desired_application,
                    desired_image,
                    previous_image=actual_image
                )

            else:
                print(
                    f"Reconciliation: {desired_application} is in sync"
                )

        except FileNotFoundError:
            print("No desired_state.json found")

        except Exception as error:
            print(f"Reconciliation error: {error}")

        time.sleep(30)

@app.get("/")
def home():
    return {
        "message": "Deployment Controller is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()

    application = payload.get("repository")
    version = payload.get("commit")
    image = payload.get("image")

    desired_state = {
        "application": application,
        "version": version,
        "image": image
    }

    with open("desired_state.json", "w") as file:
        json.dump(desired_state, file, indent=2)

    return {
        "message": "Desired state updated",
        "desired_state": desired_state
    }

def health_check(url, retries=10, delay=2):
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=2)

            if response.status_code == 200:
                data = response.json()

                if data.get("status") == "healthy":
                    return True

        except requests.exceptions.RequestException:
            pass

        time.sleep(delay)

    return False


def deploy_container(application, image, previous_image=None):

    # Remove existing container
    try:
        old_container = docker_client.containers.get(application)

        print(f"Stopping old container: {application}")
        old_container.stop()

        print(f"Removing old container: {application}")
        old_container.remove()

    except docker.errors.NotFound:
        print("No existing container found")

    try:
        docker_client.images.get(image)
        print(f"Image already exists locally: {image}")
    except docker.errors.ImageNotFound:
        print(f"Image not found locally. Pulling: {image}")
        docker_client.images.pull(image)

    # Start new container
    print(f"Starting new container with image: {image}")

    new_container = docker_client.containers.run(
        image,
        name=application,
        ports={"8000/tcp": 8000},
        detach=True
    )

    # Health check
    print("Checking application health...")

    healthy = health_check("http://localhost:8000/health")

    if healthy:
        return {
            "container": new_container.name,
            "image": image,
            "status": "healthy"
        }

    # New deployment failed
    print("New deployment is unhealthy!")

    new_container.stop()
    new_container.remove()

    # Rollback
    if previous_image:
        print(f"Rolling back to: {previous_image}")

        rollback_container = docker_client.containers.run(
            previous_image,
            name=application,
            ports={"8000/tcp": 8000},
            detach=True
        )

        rollback_healthy = health_check(
            "http://localhost:8000/health"
        )

        if rollback_healthy:
            return {
                "container": rollback_container.name,
                "image": previous_image,
                "status": "rolled_back",
                "reason": "New deployment failed health check"
            }

    return {
        "container": application,
        "image": image,
        "status": "failed"
    }


@app.post("/deploy-test")
def deploy_test():
    return deploy_container(
        "python-test-app",
        "python-test-app:1.0"
    )


@app.get("/reconcile")
def reconcile():
    with open("desired_state.json", "r") as file:
        desired_state = json.load(file)

    desired_application = desired_state["application"]
    desired_version = desired_state["version"]
    desired_image = desired_state["image"]

    containers = docker_client.containers.list()
    actual_image = None

    for container in containers:
        if container.name == desired_application:
            image_tags = container.image.tags

            if image_tags:
                actual_image = image_tags[0]

    # Application is not currently running
    if actual_image is None:
        deployment = deploy_container(
            desired_application,
            desired_image
        )

        return {
            "status": "deployed",
            "message": "Application was not running. Desired image deployed.",
            "desired": desired_state,
            "deployment": deployment
        }

    # Desired image is already running
    if desired_image == actual_image:
        return {
            "status": "in_sync",
            "message": "Desired image matches actual Docker state.",
            "desired": desired_state,
            "actual": {
                "application": desired_application,
                "image": actual_image
            }
        }

    # Application is running, but with a different image
    deployment = deploy_container(
        desired_application,
        desired_image,
        previous_image=actual_image
    )

    return {
        "status": "deployed",
        "message": "Application was out of sync. Desired image deployed.",
        "desired": desired_state,
        "previous": {
            "application": desired_application,
            "image": actual_image
        },
        "deployment": deployment
    }

@app.get("/docker-state")
def docker_state():

    containers = docker_client.containers.list()

    result = []

    for container in containers:

        result.append({
            "name": container.name,
            "image": container.image.tags,
            "status": container.status
        })

    return {
        "running_containers": result
    }

reconciler_thread = threading.Thread(
    target=reconciliation_loop,
    daemon=True
)

reconciler_thread.start()
