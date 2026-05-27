import unittest
from unittest.mock import AsyncMock, MagicMock

from core.middleware import Middleware


class TestMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_context = {
            'topic': 'test/topic',
            'payload': {'test': 'data'},
            'params': {'id': '123'},
            'client': MagicMock(),
        }

    async def test_middleware_chain(self):
        class _TestMiddleware(Middleware):
            async def handle(self, context, next_handler):
                context['modified_by'] = 'middleware'
                result = await next_handler(context)
                result['middleware_processed'] = True
                return result

        mock_handler = AsyncMock(return_value={'status': 'success'})
        middleware = _TestMiddleware()
        result = await middleware.handle(self.test_context, mock_handler)

        mock_handler.assert_called_once()
        context_arg = mock_handler.call_args[0][0]
        self.assertEqual(context_arg['modified_by'], 'middleware')
        self.assertTrue(result['middleware_processed'])
        self.assertEqual(result['status'], 'success')

    async def test_multiple_middleware_chain(self):
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

        mock_handler = AsyncMock(return_value={'status': 'success'})
        first_middleware = FirstMiddleware()
        second_middleware = SecondMiddleware()

        async def chain(context):
            return await first_middleware.handle(context, lambda ctx: second_middleware.handle(ctx, mock_handler))

        result = await chain(self.test_context)

        mock_handler.assert_called_once()
        context_arg = mock_handler.call_args[0][0]
        self.assertTrue(context_arg['first'])
        self.assertTrue(context_arg['second'])
        self.assertTrue(result['first_processed'])
        self.assertTrue(result['second_processed'])
        self.assertEqual(result['status'], 'success')

    async def test_middleware_error_handling(self):
        class ErrorHandlingMiddleware(Middleware):
            async def handle(self, context, next_handler):
                try:
                    return await next_handler(context)
                except Exception as e:
                    return {'error': str(e), 'status': 'error'}

        async def failing_handler(context):
            raise ValueError('Test error')

        middleware = ErrorHandlingMiddleware()
        result = await middleware.handle(self.test_context, failing_handler)

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'], 'Test error')


if __name__ == '__main__':
    unittest.main()
