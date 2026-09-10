from analyzer.api_analyzer import analyze_changes


def test_removed_endpoint_is_breaking():

    old_contract = {
        "paths": {
            "/users": {
                "get": {}
            }
        }
    }

    new_contract = {
        "paths": {}
    }

    result = analyze_changes(old_contract, new_contract)

    assert len(result["breaking_changes"]) == 1
    assert result["breaking_changes"][0]["type"] == "removed_endpoint"


def test_removed_required_field_is_breaking():

    old_contract = {
        "paths": {
            "/login": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "required": [
                                        "username",
                                        "password"
                                    ],
                                    "properties": {
                                        "username": {
                                            "type": "string"
                                        },
                                        "password": {
                                            "type": "string"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    new_contract = {
        "paths": {
            "/login": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "required": [
                                        "username"
                                    ],
                                    "properties": {
                                        "username": {
                                            "type": "string"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    result = analyze_changes(old_contract, new_contract)

    assert any(
        change["type"] == "removed_required_field"
        for change in result["breaking_changes"]
    )


def test_changed_field_type_is_breaking():

    old_contract = {
        "paths": {
            "/login": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "username": {
                                            "type": "string"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    new_contract = {
        "paths": {
            "/login": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "username": {
                                            "type": "integer"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    result = analyze_changes(old_contract, new_contract)

    assert any(
        change["type"] == "changed_field_type"
        for change in result["breaking_changes"]
    )


def test_added_endpoint_is_not_breaking():

    old_contract = {
        "paths": {
            "/users": {
                "get": {}
            }
        }
    }

    new_contract = {
        "paths": {
            "/users": {
                "get": {}
            },
            "/products": {
                "get": {}
            }
        }
    }

    result = analyze_changes(old_contract, new_contract)

    assert result["breaking_changes"] == []

    assert {
        "method": "GET",
        "path": "/products"
    } in result["added_endpoints"]
