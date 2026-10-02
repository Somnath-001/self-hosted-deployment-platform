from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
import json
import docker
import time
import requests
import threading

app = FastAPI(title="Deployment Controller")

docker_client = docker.from_env()

@app.get("/dashboard")
def dashboard():
    return FileResponse("../dashboard/index.html")

def reconciliation_loop():
    while True:
        try:
            with open("desired_state.json", "r") as file:
                desired_state = json.load(file)

            # Support both old single-app and new multi-app formats
            if "applications" in desired_state:
                applications = desired_state["applications"]
            else:
                application = desired_state.get("application")
                applications = {
                    application: {
                        "version": desired_state.get("version"),
                        "image": desired_state.get("image")
                    }
                } if application else {}

            for application, config in applications.items():

                desired_image = config.get("image")

                if not desired_image:
                    continue

                containers = docker_client.containers.list()

                actual_image = None

                for container in containers:
                    if container.name == application:
                        image_tags = container.image.tags

                        if image_tags:
                            actual_image = image_tags[0]

                if actual_image != desired_image:
                    print(
                        f"Reconciliation: {application} "
                        f"desired={desired_image}, "
                        f"actual={actual_image}"
                    )

                    deploy_container(
                        application,
                        desired_image,
                        previous_image=actual_image
                    )

                else:
                    print(
                        f"Reconciliation: {application} is in sync"
                    )

        except FileNotFoundError:
            print("No desired_state.json found")

        except Exception as e:
            print(f"Reconciliation error: {e}")

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

    if not application or not image:
        return {
            "message": "Invalid deployment payload",
            "status": "error"
        }

    try:
        with open("desired_state.json", "r") as file:
            desired_state = json.load(file)
    except FileNotFoundError:
        desired_state = {"applications": {}}

    # Convert old single-app format to multi-app format
    if "applications" not in desired_state:
        old_application = desired_state.get("application")

        desired_state = {
            "applications": {}
        }

        if old_application:
            desired_state["applications"][old_application] = {
                "version": desired_state.get("version"),
                "image": desired_state.get("image")
            }

    # Add/update only this application
    desired_state["applications"][application] = {
        "version": version,
        "image": image
    }

    with open("desired_state.json", "w") as file:
        json.dump(desired_state, file, indent=2)

    return {
        "message": "Desired state updated",
        "application": application,
        "desired": desired_state["applications"][application]
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

def record_release(
    application,
    version,
    image,
    status,
    reason=None
):
    history_file = "deployment_history.json"

    try:
        with open(history_file, "r") as file:
            history = json.load(file)
    except FileNotFoundError:
        history = {"releases": []}

    release = {
        "application": application,
        "version": version,
        "image": image,
        "status": status,
        "reason": reason
    }

    history["releases"].insert(0, release)

    with open(history_file, "w") as file:
        json.dump(history, file, indent=2)

def record_log(application, event, status, message=None):
    log_file = "deployment_logs.json"

    try:
        with open(log_file, "r") as file:
            logs = json.load(file)
    except FileNotFoundError:
        logs = {"logs": []}

    log = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "application": application,
        "event": event,
        "status": status,
        "message": message
    }

    logs["logs"].insert(0, log)

    # Keep latest 100 events
    logs["logs"] = logs["logs"][:100]

    with open(log_file, "w") as file:
        json.dump(logs, file, indent=2)

def get_application_port(application):
    ports = {
        "python-test-app": 8000,
        "node-test-app": 8001
    }

    return ports.get(application, 8000)


def deploy_container(application, image, previous_image=None):

    port = get_application_port(application)
    health_url = f"http://localhost:{port}/health"

    record_log(
        application,
        "deployment_started",
        "started",
        f"Deploying image {image}"
    )

    # Remove existing container
    try:
        old_container = docker_client.containers.get(application)

        print(f"Stopping old container: {application}")
        old_container.stop()

        print(f"Removing old container: {application}")
        old_container.remove()

    except docker.errors.NotFound:
        print("No existing container found")

    # Get Docker image
    try:
        docker_client.images.get(image)
        print(f"Image already exists locally: {image}")

        record_log(
            application,
            "image_ready",
            "success",
            f"Image available locally: {image}"
        )

    except docker.errors.ImageNotFound:
        print(f"Image not found locally. Pulling: {image}")

        record_log(
            application,
            "image_pull",
            "started",
            f"Pulling image {image}"
        )

        docker_client.images.pull(image)

        record_log(
            application,
            "image_pull",
            "success",
            f"Successfully pulled {image}"
        )

    # Start new container
    print(f"Starting new container with image: {image}")
    print(f"Using host port: {port}")

    new_container = docker_client.containers.run(
        image,
        name=application,
        ports={"8000/tcp": port},
        detach=True
    )

    record_log(
        application,
        "container_started",
        "success",
        f"Container started on port {port}"
    )

    # Health check
    print("Checking application health...")

    record_log(
        application,
        "health_check",
        "started",
        f"Checking {health_url}"
    )

    healthy = health_check(health_url)

    # New deployment is healthy
    if healthy:

        record_log(
            application,
            "health_check",
            "success",
            "Application is healthy"
        )

        record_log(
            application,
            "deployment_completed",
            "success",
            "Deployment completed successfully"
        )

        record_release(
            application,
            image.split(":")[-1],
            image,
            "healthy"
        )

        return {
            "container": new_container.name,
            "image": image,
            "port": port,
            "status": "healthy"
        }

    # New deployment failed
    print("New deployment is unhealthy!")

    new_container.stop()
    new_container.remove()

    record_release(
        application,
        image.split(":")[-1],
        image,
        "failed",
        "New deployment failed health check"
    )

    # Rollback
    if previous_image:

        print(f"Rolling back to: {previous_image}")

        rollback_container = docker_client.containers.run(
            previous_image,
            name=application,
            ports={"8000/tcp": port},
            detach=True
        )

        rollback_healthy = health_check(health_url)

        if rollback_healthy:

            record_release(
                application,
                previous_image.split(":")[-1],
                previous_image,
                "rolled_back",
                "New deployment failed health check"
            )

            return {
                "container": rollback_container.name,
                "image": previous_image,
                "port": port,
                "status": "rolled_back"
            }

    return {
        "container": application,
        "image": image,
        "port": port,
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

    # Support old single-app format
    if "applications" not in desired_state:
        application = desired_state.get("application")

        if application:
            desired_state = {
                "applications": {
                    application: {
                        "version": desired_state.get("version"),
                        "image": desired_state.get("image")
                    }
                }
            }
        else:
            return {
                "status": "error",
                "message": "No applications found in desired state"
            }

    results = []

    for application, config in desired_state["applications"].items():

        desired_image = config.get("image")

        if not desired_image:
            continue

        actual_image = None

        try:
            container = docker_client.containers.get(application)

            if container.image.tags:
                actual_image = container.image.tags[0]

        except docker.errors.NotFound:
            pass

        # Application is not running
        if actual_image is None:

            deployment = deploy_container(
                application,
                desired_image
            )

            results.append({
                "application": application,
                "status": "deployed",
                "deployment": deployment
            })

        # Already running desired image
        elif desired_image == actual_image:

            results.append({
                "application": application,
                "status": "in_sync",
                "image": actual_image
            })

        # Running different image
        else:

            deployment = deploy_container(
                application,
                desired_image,
                previous_image=actual_image
            )

            results.append({
                "application": application,
                "status": "deployed",
                "previous_image": actual_image,
                "deployment": deployment
            })

    return {
        "status": "completed",
        "applications": results
    }

@app.post("/applications/{application}/stop")
def stop_application(application: str):
    try:
        container = docker_client.containers.get(application)
        container.stop()

        return {
            "application": application,
            "status": "stopped"
        }

    except docker.errors.NotFound:
        return {
            "application": application,
            "status": "error",
            "message": "Application container not found"
        }


@app.post("/applications/{application}/start")
def start_application(application: str):
    try:
        container = docker_client.containers.get(application)
        container.start()

        return {
            "application": application,
            "status": "started"
        }

    except docker.errors.NotFound:
        return {
            "application": application,
            "status": "error",
            "message": "Application container not found"
        }


@app.post("/applications/{application}/restart")
def restart_application(application: str):
    try:
        container = docker_client.containers.get(application)
        container.restart()

        return {
            "application": application,
            "status": "restarted"
        }

    except docker.errors.NotFound:
        return {
            "application": application,
            "status": "error",
            "message": "Application container not found"
        }


@app.delete("/applications/{application}")
def delete_application(application: str):
    try:
        container = docker_client.containers.get(application)

        container.stop()
        container.remove()

        return {
            "application": application,
            "status": "deleted"
        }

    except docker.errors.NotFound:
        return {
            "application": application,
            "status": "error",
            "message": "Application container not found"
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

@app.get("/status")
def status():
    try:
        with open("desired_state.json", "r") as file:
            desired_state = json.load(file)
    except FileNotFoundError:
        desired_state = {}

    # Support old single-app format
    if "applications" not in desired_state:
        application = desired_state.get("application")

        if not application:
            return {
                "applications": []
            }

        desired_state = {
            "applications": {
                application: {
                    "version": desired_state.get("version"),
                    "image": desired_state.get("image")
                }
            }
        }

    results = []

    for application, config in desired_state["applications"].items():

        desired_image = config.get("image")
        desired_version = config.get("version")

        actual_image = None
        container_status = "not_running"
        health = "unknown"

        try:
            container = docker_client.containers.get(application)

            container_status = container.status

            if container.image.tags:
                actual_image = container.image.tags[0]

        except docker.errors.NotFound:
            pass

        if container_status == "running":
            try:
                port = get_application_port(application)

                response = requests.get(
                    f"http://localhost:{port}/health",
                    timeout=2
                )

                if response.status_code == 200:
                    data = response.json()
                    health = data.get("status", "unknown")

            except requests.exceptions.RequestException:
                health = "unhealthy"

        results.append({
            "application": application,
            "desired_version": desired_version,
            "desired_image": desired_image,
            "actual_image": actual_image,
            "container_status": container_status,
            "health": health,
            "in_sync": (
                desired_image == actual_image
                and actual_image is not None
            )
        })

    return {
        "applications": results
    }

@app.get("/logs")
def get_logs():
    try:
        with open("deployment_logs.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"logs": []}

@app.get("/history")
def deployment_history():

    try:
        with open("deployment_history.json", "r") as file:
            history = json.load(file)

    except FileNotFoundError:
        history = {
            "releases": []
        }

    return history

reconciler_thread = threading.Thread(
    target=reconciliation_loop,
    daemon=True
)

reconciler_thread.start()
