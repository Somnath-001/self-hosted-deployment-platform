import json
import sys


def load_contract(file_path):
    with open(file_path, "r") as file:
        return json.load(file)


def get_endpoints(contract):
    endpoints = set()

    for path, methods in contract.get("paths", {}).items():
        for method in methods:
            if method.lower() in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head"
            }:
                endpoints.add((method.upper(), path))

    return endpoints


def get_required_fields(contract, method, path):
    endpoint = contract["paths"][path].get(method.lower(), {})

    request_body = endpoint.get("requestBody", {})

    content = request_body.get("content", {})
    json_content = content.get("application/json", {})

    schema = json_content.get("schema", {})

    return set(schema.get("required", []))

def get_field_types(contract, method, path):
    endpoint = contract["paths"][path].get(method.lower(), {})

    request_body = endpoint.get("requestBody", {})

    content = request_body.get("content", {})
    json_content = content.get("application/json", {})

    schema = json_content.get("schema", {})

    properties = schema.get("properties", {})

    return {
        field: details.get("type")
        for field, details in properties.items()
    }

def analyze_changes(old_contract, new_contract):

    old_endpoints = get_endpoints(old_contract)
    new_endpoints = get_endpoints(new_contract)

    removed_endpoints = old_endpoints - new_endpoints
    added_endpoints = new_endpoints - old_endpoints

    breaking_changes = []

    # Check for removed endpoints
    for method, path in sorted(removed_endpoints):
        breaking_changes.append({
            "type": "removed_endpoint",
            "method": method,
            "path": path
        })

    # Check for removed required fields
    common_endpoints = old_endpoints & new_endpoints

    for method, path in sorted(common_endpoints):

        old_required = get_required_fields(
            old_contract,
            method,
            path
        )

        new_required = get_required_fields(
            new_contract,
            method,
            path
        )

        removed_required = old_required - new_required

        for field in sorted(removed_required):
            breaking_changes.append({
                "type": "removed_required_field",
                "method": method,
                "path": path,
                "field": field
            })
        old_types = get_field_types(
            old_contract,
            method,
            path
        )

        new_types = get_field_types(
            new_contract,
            method,
            path
        )

        common_fields = set(old_types) & set(new_types)

        for field in sorted(common_fields):

            if old_types[field] != new_types[field]:

                breaking_changes.append({
                    "type": "changed_field_type",
                    "method": method,
                    "path": path,
                    "field": field,
                    "old_type": old_types[field],
                    "new_type": new_types[field]
                })

    return {
        "breaking_changes": breaking_changes,

        "added_endpoints": [
            {
                "method": method,
                "path": path
            }
            for method, path in sorted(added_endpoints)
        ]
    }


def main():

    if len(sys.argv) != 3:
        print(
            "Usage: python api_analyzer.py "
            "<old_contract.json> <new_contract.json>"
        )
        sys.exit(1)

    old_contract = load_contract(sys.argv[1])
    new_contract = load_contract(sys.argv[2])

    result = analyze_changes(
        old_contract,
        new_contract
    )

    print(json.dumps(result, indent=2))

    if result["breaking_changes"]:
        print("\n❌ Breaking API changes detected!")
        sys.exit(1)

    print("\n✅ No breaking API changes detected.")


if __name__ == "__main__":
    main()
