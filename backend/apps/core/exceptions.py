from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Wrap DRF exceptions in the project-standard error envelope:
        {"error": "<code>", "message": "<human text>", "details": {...}}
    """
    response = exception_handler(exc, context)

    if response is None:
        return response

    data = response.data

    if isinstance(data, dict) and "detail" in data:
        response.data = {
            "error": getattr(exc, "default_code", "error"),
            "message": str(data["detail"]),
            "details": {},
        }
    elif isinstance(data, list):
        response.data = {
            "error": "validation_error",
            "message": "Validation failed.",
            "details": {"non_field_errors": data},
        }
    elif isinstance(data, dict):
        response.data = {
            "error": "validation_error",
            "message": "Validation failed.",
            "details": data,
        }

    return response
