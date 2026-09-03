import time
import logging

logger = logging.getLogger(__name__)

class RequestTimeoutMiddleware:
    """Handle slow requests and prevent hanging"""

    TIMEOUT_ENDPOINTS = [
        '/apply/',
        '/register/',
        '/login/',
        '/payment/',
        '/quickbooks/sync/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        should_timeout = any(
            request.path.startswith(endpoint)
            for endpoint in self.TIMEOUT_ENDPOINTS
        )

        if should_timeout:
            start_time = time.time()

            try:
                response = self.get_response(request)
                elapsed = time.time() - start_time

                if elapsed > 10:
                    logger.warning(f"⚠️ Slow endpoint: {request.path} took {elapsed:.2f}s")
                return response

            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"❌ Request failed after {elapsed:.2f}s: {e}")

                # ✅ If the client disconnected, return a graceful response
                return HttpResponse(
                    "Request timed out. Please try again.",
                    status=408,
                    content_type="text/plain"
                )

        return self.get_response(request)

class DatabaseRetryMiddleware:
    """
    Retry database operations on connection errors.
    No external dependencies needed.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_retries = 3
        self.delay = 0.5

    def __call__(self, request):
        for attempt in range(self.max_retries):
            try:
                # ✅ Try to process the request
                response = self.get_response(request)
                return response

            except Exception as e:
                # ✅ Check if it's a database error
                error_str = str(e).lower()
                if any(err in error_str for err in [
                    'operationalerror',
                    'interfaceerror',
                    'internalerror',
                    'gone away',
                    'connection already closed',
                    'mysql server has gone away'
                ]):
                    # ✅ Close old connections before retry
                    close_old_connections()

                    if attempt == self.max_retries - 1:
                        # ✅ Last attempt failed
                        logger.error(f"Database error after {self.max_retries} attempts: {e}")
                        raise

                    # ✅ Log and retry
                    logger.warning(
                        f"Database error (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {self.delay * (attempt + 1):.2f}s..."
                    )
                    time.sleep(self.delay * (attempt + 1))  # Increasing delay
                else:
                    # ✅ Not a database error, raise it
                    raise