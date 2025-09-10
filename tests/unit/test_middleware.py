import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.middleware import Middleware


class TestMiddleware(unittest.TestCase):
    def setUp(self):
        self.test_context = {
            'topic': 'test/topic',
            'payload': {'test': 'data'},
            'params': {'id': '123'},
            'client': MagicMock()
        }

    def test_middleware_chain(self):
        """Test that middleware correctly chains and processes context."""
        # Create a test middleware class
        class TestMiddleware(Middleware):
            async def handle(self, context, next_handler):
                # Modify the context
                context['modified_by'] = 'middleware'
                # Call the next handler
                result = await next_handler(context)
                # Modify the result
                result['middleware_processed'] = True
                return result

        # Create a mock handler that will be called after middleware
        mock_handler = AsyncMock(return_value={'status': 'success'})

        # Create and execute the middleware
        middleware = TestMiddleware()

        # Run the middleware chain
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            middleware.handle(self.test_context, mock_handler)
        )

        # Check that the handler was called with the modified context
        mock_handler.assert_called_once()
        context_arg = mock_handler.call_args[0][0]
        self.assertEqual(context_arg['modified_by'], 'middleware')

        # Check that the result was modified by the middleware
        self.assertTrue(result['middleware_processed'])
        self.assertEqual(result['status'], 'success')

    def test_multiple_middleware_chain(self):
        """Test that multiple middleware components correctly chain together."""
        # Create test middleware classes
        class FirstMiddleware(Middleware):
            async def handle(self, context, next_handler):
                context['first'] = True
                result = await next_handler(context)
                result['first_processed'] = True
                return result

        class SecondMiddleware(Middleware):
            async def handle(self, context, next_handler):
                context['second'] = True
                result = await next_handler(context)
                result['second_processed'] = True
                return result

        # Create a mock handler
        mock_handler = AsyncMock(return_value={'status': 'success'})

        # Create and chain middlewares
        first_middleware = FirstMiddleware()
        second_middleware = SecondMiddleware()

        # Create the nested middleware chain manually
        async def chain(context):
            return await first_middleware.handle(context,
                lambda ctx: second_middleware.handle(ctx, mock_handler)
            )

        # Run the middleware chain
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(chain(self.test_context))

        # Check that the context was modified by both middlewares
        mock_handler.assert_called_once()
        context_arg = mock_handler.call_args[0][0]
        self.assertTrue(context_arg['first'])
        self.assertTrue(context_arg['second'])

        # Check that the result was modified by both middlewares
        self.assertTrue(result['first_processed'])
        self.assertTrue(result['second_processed'])
        self.assertEqual(result['status'], 'success')

    def test_middleware_error_handling(self):
        """Test that middleware can handle errors from handlers."""
        # Create a middleware that catches exceptions
        class ErrorHandlingMiddleware(Middleware):
            async def handle(self, context, next_handler):
                try:
                    return await next_handler(context)
                except Exception as e:
                    return {'error': str(e), 'status': 'error'}

        # Create a mock handler that raises an exception
        async def failing_handler(context):
            raise ValueError("Test error")

        # Create and execute the middleware
        middleware = ErrorHandlingMiddleware()

        # Run the middleware with the failing handler
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            middleware.handle(self.test_context, failing_handler)
        )

        # Check that the middleware caught the exception and returned an error response
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'], 'Test error')


if __name__ == "__main__":
    unittest.main()
