import logging
from threading import local
import uuid
_locals = local()


class Request():

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["X-Request-ID"] = uuid.uuid4()
        _locals.request_id = request.META["X-Request-ID"]
        response = self.get_response(request)
        return response


class RequestFilter(logging.Filter):

    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = ""
        if hasattr(_locals, 'request_id'):
            record.request_id = _locals.request_id
        return True