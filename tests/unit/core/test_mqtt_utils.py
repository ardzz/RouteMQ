import os
import unittest
from unittest.mock import MagicMock, patch

from routemq import observability
from routemq.mqtt_utils import (
    MqttTlsConfig,
    build_worker_broker_config,
    build_worker_client_id,
    connect_mqtt_client_with_retries,
    create_mqtt_client,
    extract_trace_context,
    get_main_client_id,
    get_mqtt_connection_config,
    get_mqtt_group_name,
    get_mqtt_retry_config,
    get_mqtt_tls_config,
    get_worker_client_id_prefix,
    inject_trace_context,
    is_network_startup_error,
    parse_mqtt_payload,
    wrap_mqtt_publish_with_trace_context,
    _client_supports_user_properties,
    _last_user_property,
    _looks_like_user_property,
    _new_publish_properties,
    _parse_traceparent,
    _set_user_property,
    _user_property_pairs,
    _valid_hex,
    _valid_trace_flags,
)


class MqttTlsConfigTests(unittest.TestCase):
    def test_connection_config_reads_central_settings(self) -> None:
        with patch.dict(
            os.environ,
            {
                'MQTT_BROKER': 'broker.local',
                'MQTT_PORT': '1884',
                'MQTT_USERNAME': 'user',
                'MQTT_PASSWORD': 'secret',
            },
            clear=True,
        ):
            config = get_mqtt_connection_config()

        self.assertEqual(config.broker, 'broker.local')
        self.assertEqual(config.port, 1884)
        self.assertEqual(config.username, 'user')
        self.assertEqual(config.password, 'secret')

    def test_client_id_and_group_helpers_read_central_settings(self) -> None:
        with patch.dict(os.environ, {'MQTT_CLIENT_ID': 'client', 'MQTT_GROUP_NAME': 'group'}, clear=True):
            self.assertEqual(get_main_client_id(), 'client')
            self.assertEqual(get_worker_client_id_prefix(), 'client')
            self.assertEqual(get_mqtt_group_name(), 'group')

    def test_tls_config_defaults_to_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = get_mqtt_tls_config()

        self.assertFalse(config.enabled)

    def test_create_client_applies_tls_then_insecure(self) -> None:
        fake_client = MagicMock()
        calls: list[str] = []
        fake_client.tls_set.side_effect = lambda **kwargs: calls.append('tls_set')
        fake_client.tls_insecure_set.side_effect = lambda value: calls.append('tls_insecure_set')

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client(
                'client',
                on_connect=MagicMock(),
                on_message=MagicMock(),
                tls_config=MqttTlsConfig(
                    enabled=True,
                    ca_certs='ca.pem',
                    certfile='cert.pem',
                    keyfile='key.pem',
                    insecure=True,
                ),
            )

        fake_client.tls_set.assert_called_once_with(ca_certs='ca.pem', certfile='cert.pem', keyfile='key.pem')
        fake_client.tls_insecure_set.assert_called_once_with(True)
        self.assertEqual(calls, ['tls_set', 'tls_insecure_set'])

    def test_create_client_uses_new_style_paho_exponential_backoff_when_supported(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None
                self.reconnect_kwargs = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120, exponential_backoff=False) -> None:
                self.reconnect_kwargs = {
                    'min_delay': min_delay,
                    'max_delay': max_delay,
                    'exponential_backoff': exponential_backoff,
                }

        fake_client = FakeClient()

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.dict(
                os.environ,
                {'MQTT_CONNECT_RETRIES': '3', 'MQTT_RETRY_MIN_DELAY': '2', 'MQTT_RETRY_MAX_DELAY': '9'},
                clear=True,
            ),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())

        self.assertEqual(
            fake_client.reconnect_kwargs,
            {'min_delay': 2.0, 'max_delay': 9.0, 'exponential_backoff': True},
        )

    def test_create_client_supports_old_style_paho_reconnect_delays(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None
                self.reconnect_kwargs = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120) -> None:
                self.reconnect_kwargs = {'min_delay': min_delay, 'max_delay': max_delay}

        fake_client = FakeClient()

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch.dict(
                os.environ,
                {'MQTT_CONNECT_RETRIES': '3', 'MQTT_RETRY_MIN_DELAY': '2', 'MQTT_RETRY_MAX_DELAY': '9'},
                clear=True,
            ),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())

        self.assertEqual(fake_client.reconnect_kwargs, {'min_delay': 2.0, 'max_delay': 9.0})

    def test_create_client_does_not_swallow_reconnect_delay_errors(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120) -> None:
                raise RuntimeError('paho internal error')

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=FakeClient()),
            self.assertRaises(RuntimeError),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())

    def test_create_client_skips_tls_insecure_when_not_enabled(self) -> None:
        fake_client = MagicMock()

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client(
                'client',
                on_connect=MagicMock(),
                on_message=MagicMock(),
                tls_config=MqttTlsConfig(enabled=True, insecure=False),
            )

        fake_client.tls_insecure_set.assert_not_called()

    def test_create_client_skips_reconnect_delay_when_not_supported(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None

        fake_client = FakeClient()

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())

        self.assertFalse(hasattr(fake_client, 'reconnect_delay_set'))


class MqttRetryTests(unittest.TestCase):
    def test_retry_config_reads_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                'MQTT_CONNECT_RETRIES': '4',
                'MQTT_RETRY_MIN_DELAY': '0.5',
                'MQTT_RETRY_MAX_DELAY': '5',
                'MQTT_RETRY_JITTER': '1',
            },
            clear=True,
        ):
            config = get_mqtt_retry_config()

        self.assertEqual(config.max_attempts, 4)
        self.assertEqual(config.min_delay, 0.5)
        self.assertEqual(config.max_delay, 5)
        self.assertEqual(config.jitter, 1)

    def test_connect_retries_network_startup_errors_with_fake_sleep(self) -> None:
        fake_client = MagicMock()
        fake_client.connect.side_effect = [ConnectionRefusedError('down'), None]
        sleeps: list[float] = []

        with patch.dict(os.environ, {'MQTT_CONNECT_RETRIES': '2', 'MQTT_RETRY_MIN_DELAY': '3'}, clear=True):
            connect_mqtt_client_with_retries(fake_client, 'broker', 1883, sleep=sleeps.append)

        self.assertEqual(fake_client.connect.call_count, 2)
        self.assertEqual(sleeps, [3.0])

    def test_connect_does_not_retry_non_network_errors(self) -> None:
        fake_client = MagicMock()
        fake_client.connect.side_effect = RuntimeError('bad')
        sleeps: list[float] = []

        with self.assertRaises(RuntimeError):
            connect_mqtt_client_with_retries(fake_client, 'broker', 1883, sleep=sleeps.append)

        self.assertEqual(sleeps, [])


class MqttTraceContextTests(unittest.TestCase):
    def tearDown(self) -> None:
        observability.clear_hooks()
        super().tearDown()

    def test_v5_user_properties_round_trip_active_span_trace_context(self) -> None:
        class Properties:
            pass

        client = MagicMock()
        client._protocol = 5
        properties = Properties()
        token = observability.set_context({'tracestate': 'dd=s:1'})

        try:
            with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
                with observability.start_span('mqtt.parent') as span:
                    assert span is not None
                    injected = inject_trace_context(client, properties)
                    extracted = extract_trace_context(MagicMock(properties=injected))
        finally:
            observability.reset_context(token)

        self.assertIs(injected, properties)
        self.assertEqual(extracted['trace_id'], span.trace_id)
        self.assertEqual(extracted['span_id'], span.span_id)
        self.assertEqual(extracted['trace_flags'], span.trace_flags)
        self.assertEqual(extracted['tracestate'], 'dd=s:1')

    def test_v311_publish_wrapper_does_not_add_trace_properties_or_touch_payload(self) -> None:
        client = MagicMock()
        client._protocol = 4
        client._routemq_trace_publish_wrapped = False
        client.publish = MagicMock(return_value=MagicMock(mid=17))
        original_publish = client.publish

        wrap_mqtt_publish_with_trace_context(client)
        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            result = client.publish('devices/1', b'{"secret":"payload"}')

        self.assertEqual(result.mid, 17)
        original_publish.assert_called_once_with('devices/1', b'{"secret":"payload"}')

    def test_extract_trace_context_ignores_invalid_traceparent(self) -> None:
        properties = MagicMock(UserProperty=[('traceparent', '00-not-valid-span-01')])

        self.assertEqual(extract_trace_context(MagicMock(properties=properties)), {})

    def test_inject_trace_context_no_op_for_v311(self) -> None:
        client = MagicMock()
        client._protocol = 4
        properties = MagicMock()

        result = inject_trace_context(client, properties)

        self.assertIs(result, properties)

    def test_inject_trace_context_no_op_when_no_active_span(self) -> None:
        client = MagicMock()
        client._protocol = 5
        properties = MagicMock()

        with patch.dict(os.environ, {'ENABLE_TRACING': 'false'}):
            result = inject_trace_context(client, properties)

        self.assertIs(result, properties)

    def test_inject_trace_context_creates_new_properties_when_none(self) -> None:
        client = MagicMock()
        client._protocol = 5

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                result = inject_trace_context(client, None)

        self.assertIsNotNone(result)
        self.assertEqual(result.UserProperty[0][0], 'traceparent')

    def test_inject_trace_context_returns_original_when_new_properties_fails(self) -> None:
        client = MagicMock()
        client._protocol = 5
        original = MagicMock()

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                with patch('routemq.mqtt_utils._new_publish_properties', return_value=None):
                    result = inject_trace_context(client, original)

        self.assertIs(result, original)

    def test_inject_trace_context_skips_tracestate_when_absent(self) -> None:
        client = MagicMock()
        client._protocol = 5
        properties = MagicMock()
        properties.UserProperty = []

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                result = inject_trace_context(client, properties)

        user_props = _user_property_pairs(result)
        self.assertEqual([k for k, _ in user_props], ['traceparent'])

    def test_extract_trace_context_returns_empty_when_no_properties(self) -> None:
        message = MagicMock()
        message.properties = None

        self.assertEqual(extract_trace_context(message), {})

    def test_extract_trace_context_returns_empty_when_no_traceparent(self) -> None:
        properties = MagicMock(UserProperty=[('other', 'value')])

        self.assertEqual(extract_trace_context(MagicMock(properties=properties)), {})

    def test_extract_trace_context_omits_tracestate_when_absent(self) -> None:
        traceparent = '00-' + 'a' * 32 + '-' + 'b' * 16 + '-01'
        properties = MagicMock(UserProperty=[('traceparent', traceparent)])

        result = extract_trace_context(MagicMock(properties=properties))

        self.assertNotIn('tracestate', result)

    def test_wrap_mqtt_publish_already_wrapped_returns_early(self) -> None:
        client = MagicMock()
        client._routemq_trace_publish_wrapped = True

        result = wrap_mqtt_publish_with_trace_context(client)

        self.assertIs(result, client)

    def test_wrap_mqtt_publish_non_callable_publish_returns_early(self) -> None:
        client = MagicMock()
        client._routemq_trace_publish_wrapped = False
        client.publish = 'not_callable'

        result = wrap_mqtt_publish_with_trace_context(client)

        self.assertIs(result, client)

    def test_wrap_mqtt_publish_injects_properties_via_kwargs(self) -> None:
        client = MagicMock()
        client._protocol = 5
        client._routemq_trace_publish_wrapped = False
        original_publish = MagicMock(return_value=MagicMock(mid=42))
        client.publish = original_publish
        properties = MagicMock()
        properties.UserProperty = []

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                wrapped = wrap_mqtt_publish_with_trace_context(client)
                wrapped.publish('topic', b'payload', qos=1, retain=False, properties=properties)

        original_publish.assert_called_once()
        call_args = original_publish.call_args
        self.assertIs(call_args.kwargs['properties'], properties)

    def test_wrap_mqtt_publish_injects_properties_via_positional_args(self) -> None:
        client = MagicMock()
        client._protocol = 5
        client._routemq_trace_publish_wrapped = False
        original_publish = MagicMock(return_value=MagicMock(mid=42))
        client.publish = original_publish
        properties = MagicMock()
        properties.UserProperty = []

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                wrapped = wrap_mqtt_publish_with_trace_context(client)
                wrapped.publish('topic', b'payload', 1, False, properties)

        original_publish.assert_called_once()
        call_args = original_publish.call_args
        self.assertEqual(call_args.args[4], properties)

    def test_wrap_mqtt_publish_creates_properties_when_none_provided(self) -> None:
        client = MagicMock()
        client._protocol = 5
        client._routemq_trace_publish_wrapped = False
        original_publish = MagicMock(return_value=MagicMock(mid=42))
        client.publish = original_publish

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                wrapped = wrap_mqtt_publish_with_trace_context(client)
                wrapped.publish('topic', b'payload')

        original_publish.assert_called_once()
        call_args = original_publish.call_args
        self.assertIn('properties', call_args.kwargs)

    def test_wrap_mqtt_publish_sets_message_id_attribute(self) -> None:
        client = MagicMock()
        client._protocol = 5
        client._routemq_trace_publish_wrapped = False
        original_publish = MagicMock(return_value=MagicMock(mid=99))
        client.publish = original_publish
        inner_span = None

        original_start_span = observability.start_span

        def capture_start_span(*args, **kwargs):
            nonlocal inner_span
            scope = original_start_span(*args, **kwargs)
            inner_span = scope.__enter__()
            return _FakeSpanScope(inner_span)

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with patch('routemq.mqtt_utils.start_span', side_effect=capture_start_span):
                with observability.start_span('mqtt.parent') as span:
                    wrapped = wrap_mqtt_publish_with_trace_context(client)
                    wrapped.publish('topic', b'payload')

        self.assertIsNotNone(inner_span)
        self.assertEqual(inner_span.attributes.get('messaging.message.id'), '99')

    def test_wrap_mqtt_publish_no_message_id_when_result_has_no_mid(self) -> None:
        client = MagicMock()
        client._protocol = 5
        client._routemq_trace_publish_wrapped = False
        original_publish = MagicMock(return_value=MagicMock())
        del original_publish.return_value.mid
        client.publish = original_publish
        inner_span = None

        original_start_span = observability.start_span

        def capture_start_span(*args, **kwargs):
            nonlocal inner_span
            scope = original_start_span(*args, **kwargs)
            inner_span = scope.__enter__()
            return _FakeSpanScope(inner_span)

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with patch('routemq.mqtt_utils.start_span', side_effect=capture_start_span):
                with observability.start_span('mqtt.parent') as span:
                    wrapped = wrap_mqtt_publish_with_trace_context(client)
                    wrapped.publish('topic', b'payload')

        self.assertIsNotNone(inner_span)
        self.assertNotIn('messaging.message.id', inner_span.attributes)

    def test_wrap_mqtt_publish_skips_properties_when_new_properties_fails(self) -> None:
        client = MagicMock()
        client._protocol = 5
        client._routemq_trace_publish_wrapped = False
        original_publish = MagicMock(return_value=MagicMock(mid=42))
        client.publish = original_publish

        with patch.dict(os.environ, {'ENABLE_TRACING': 'true'}):
            with observability.start_span('mqtt.parent') as span:
                with patch('routemq.mqtt_utils._new_publish_properties', return_value=None):
                    wrapped = wrap_mqtt_publish_with_trace_context(client)
                    wrapped.publish('topic', b'payload')

        original_publish.assert_called_once_with('topic', b'payload')


class _FakeSpanScope:
    def __init__(self, span):
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if isinstance(exc_value, BaseException):
                self.span.record_exception(exc_value)
            self.span.end()
        finally:
            pass
        return None


class MqttHelperTests(unittest.TestCase):
    def test_parse_mqtt_payload_invalid_json_returns_raw_bytes(self) -> None:
        payload = b'not json'
        result = parse_mqtt_payload(payload)
        self.assertEqual(result, payload)

    def test_parse_mqtt_payload_non_utf8_returns_raw_bytes(self) -> None:
        payload = b'\xff\xfe'
        result = parse_mqtt_payload(payload)
        self.assertEqual(result, payload)

    def test_build_worker_broker_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                'MQTT_BROKER': 'broker.local',
                'MQTT_PORT': '1884',
                'MQTT_USERNAME': 'user',
                'MQTT_PASSWORD': 'secret',
                'MQTT_CLIENT_ID': 'client',
            },
            clear=True,
        ):
            config = build_worker_broker_config()

        self.assertEqual(config['broker'], 'broker.local')
        self.assertEqual(config['port'], '1884')
        self.assertEqual(config['username'], 'user')
        self.assertEqual(config['password'], 'secret')
        self.assertEqual(config['client_id_prefix'], 'client')

    def test_build_worker_client_id(self) -> None:
        worker_id = 7
        prefix = 'testworker'
        result = build_worker_client_id(worker_id, prefix)

        self.assertTrue(result.startswith(f'{prefix}-{worker_id}-'))
        self.assertEqual(len(result.split('-')), 3)

    def test_create_client_sets_on_disconnect(self) -> None:
        fake_client = MagicMock()
        on_disconnect = MagicMock()

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client(
                'client',
                on_connect=MagicMock(),
                on_message=MagicMock(),
                on_disconnect=on_disconnect,
            )

        self.assertEqual(fake_client.on_disconnect, on_disconnect)

    def test_create_client_sets_username_password(self) -> None:
        fake_client = MagicMock()

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client(
                'client',
                on_connect=MagicMock(),
                on_message=MagicMock(),
                username='user',
                password='secret',
            )

        fake_client.username_pw_set.assert_called_once_with('user', 'secret')

    def test_create_client_tls_insecure_when_enabled(self) -> None:
        fake_client = MagicMock()
        calls: list[str] = []
        fake_client.tls_set.side_effect = lambda **kwargs: calls.append('tls_set')
        fake_client.tls_insecure_set.side_effect = lambda value: calls.append('tls_insecure_set')

        with patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client):
            create_mqtt_client(
                'client',
                on_connect=MagicMock(),
                on_message=MagicMock(),
                tls_config=MqttTlsConfig(
                    enabled=True,
                    insecure=True,
                ),
            )

        self.assertEqual(calls, ['tls_set', 'tls_insecure_set'])

    def test_create_client_reconnect_delay_signature_error_path(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.on_connect = None
                self.on_message = None

            def reconnect_delay_set(self, *, min_delay=1, max_delay=120) -> None:
                pass

        fake_client = FakeClient()

        with (
            patch('routemq.mqtt_utils.mqtt_client.Client', return_value=fake_client),
            patch('routemq.mqtt_utils.signature', side_effect=TypeError('no signature')),
            patch.dict(
                os.environ,
                {'MQTT_CONNECT_RETRIES': '3', 'MQTT_RETRY_MIN_DELAY': '2', 'MQTT_RETRY_MAX_DELAY': '9'},
                clear=True,
            ),
        ):
            create_mqtt_client('client', on_connect=MagicMock(), on_message=MagicMock())


class MqttTraceHelperTests(unittest.TestCase):
    def test_client_supports_user_properties_v5(self) -> None:
        client = MagicMock()
        client._protocol = 5
        self.assertTrue(_client_supports_user_properties(client))

    def test_client_supports_user_properties_v311(self) -> None:
        client = MagicMock()
        client._protocol = 4
        self.assertFalse(_client_supports_user_properties(client))

    def test_new_publish_properties(self) -> None:
        props = _new_publish_properties()
        self.assertIsNotNone(props)

    def test_set_user_property(self) -> None:
        class Props:
            UserProperty = [('other', 'value')]

        properties = Props()
        _set_user_property(properties, 'traceparent', '00-abc')
        self.assertEqual(properties.UserProperty, [('other', 'value'), ('traceparent', '00-abc')])

    def test_set_user_property_overwrites_existing(self) -> None:
        class Props:
            UserProperty = [('traceparent', 'old')]

        properties = Props()
        _set_user_property(properties, 'traceparent', 'new')
        self.assertEqual(properties.UserProperty, [('traceparent', 'new')])

    def test_user_property_pairs_none_properties(self) -> None:
        self.assertEqual(_user_property_pairs(None), [])

    def test_user_property_pairs_none_raw(self) -> None:
        properties = MagicMock()
        properties.UserProperty = None
        self.assertEqual(_user_property_pairs(properties), [])

    def test_user_property_pairs_non_iterable_raw(self) -> None:
        properties = MagicMock()
        properties.UserProperty = 123
        self.assertEqual(_user_property_pairs(properties), [])

    def test_user_property_pairs_single_tuple(self) -> None:
        properties = MagicMock()
        properties.UserProperty = ('key', 'value')
        self.assertEqual(_user_property_pairs(properties), [('key', 'value')])

    def test_user_property_pairs_list_of_tuples(self) -> None:
        properties = MagicMock()
        properties.UserProperty = [('k1', 'v1'), ('k2', 'v2')]
        self.assertEqual(_user_property_pairs(properties), [('k1', 'v1'), ('k2', 'v2')])

    def test_user_property_pairs_skips_invalid_items(self) -> None:
        properties = MagicMock()
        properties.UserProperty = [('k1', 'v1'), 123, ('k2', 'v2')]
        self.assertEqual(_user_property_pairs(properties), [('k1', 'v1'), ('k2', 'v2')])

    def test_looks_like_user_property(self) -> None:
        self.assertTrue(_looks_like_user_property(['k', 'v']))
        self.assertTrue(_looks_like_user_property(('k', 'v')))
        self.assertFalse(_looks_like_user_property('not a pair'))
        self.assertFalse(_looks_like_user_property(['k']))
        self.assertFalse(_looks_like_user_property([1, 'v']))

    def test_last_user_property_found(self) -> None:
        self.assertEqual(_last_user_property([('a', '1'), ('b', '2'), ('a', '3')], 'a'), '3')

    def test_last_user_property_not_found(self) -> None:
        self.assertIsNone(_last_user_property([('a', '1')], 'b'))

    def test_parse_traceparent_empty(self) -> None:
        self.assertEqual(_parse_traceparent(''), {})
        self.assertEqual(_parse_traceparent(None), {})

    def test_parse_traceparent_wrong_part_count(self) -> None:
        self.assertEqual(_parse_traceparent('00-abc'), {})
        self.assertEqual(_parse_traceparent('00-abc-def-ghi-jkl'), {})

    def test_parse_traceparent_wrong_version(self) -> None:
        self.assertEqual(_parse_traceparent('01-' + 'a' * 32 + '-' + 'b' * 16 + '-01'), {})

    def test_parse_traceparent_invalid_hex(self) -> None:
        self.assertEqual(_parse_traceparent('00-gggggggggggggggggggggggggggggggg-' + 'b' * 16 + '-01'), {})
        self.assertEqual(_parse_traceparent('00-' + 'a' * 32 + '-gggggggggggggggg-01'), {})
        self.assertEqual(_parse_traceparent('00-' + 'a' * 32 + '-' + 'b' * 16 + '-gg'), {})

    def test_parse_traceparent_all_zeros(self) -> None:
        self.assertEqual(_parse_traceparent('00-' + '0' * 32 + '-' + 'b' * 16 + '-01'), {})
        self.assertEqual(_parse_traceparent('00-' + 'a' * 32 + '-' + '0' * 16 + '-01'), {})

    def test_parse_traceparent_valid(self) -> None:
        result = _parse_traceparent('00-' + 'A' * 32 + '-' + 'B' * 16 + '-01')
        self.assertEqual(result['trace_id'], 'a' * 32)
        self.assertEqual(result['span_id'], 'b' * 16)
        self.assertEqual(result['trace_flags'], '01')

    def test_valid_hex(self) -> None:
        self.assertTrue(_valid_hex('a' * 32, 32))
        self.assertFalse(_valid_hex('a' * 31, 32))
        self.assertFalse(_valid_hex('gg' * 16, 32))
        self.assertFalse(_valid_hex('0' * 32, 32))

    def test_valid_trace_flags(self) -> None:
        self.assertTrue(_valid_trace_flags('01'))
        self.assertFalse(_valid_trace_flags('1'))
        self.assertFalse(_valid_trace_flags('gg'))


class MqttNetworkErrorTests(unittest.TestCase):
    def test_is_network_startup_error_connection_refused(self) -> None:
        self.assertTrue(is_network_startup_error(ConnectionRefusedError()))

    def test_is_network_startup_error_timeout(self) -> None:
        self.assertTrue(is_network_startup_error(TimeoutError()))

    def test_is_network_startup_error_socket_timeout(self) -> None:
        import socket

        self.assertTrue(is_network_startup_error(socket.timeout()))

    def test_is_network_startup_error_socket_gaierror(self) -> None:
        import socket

        self.assertTrue(is_network_startup_error(socket.gaierror()))

    def test_is_network_startup_error_generic_connection_error(self) -> None:
        self.assertTrue(is_network_startup_error(ConnectionError()))

    def test_is_network_startup_error_oserror_errno_codes(self) -> None:
        import errno

        for code in [
            errno.ECONNREFUSED,
            errno.ETIMEDOUT,
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.ECONNRESET,
            errno.ECONNABORTED,
            errno.EADDRNOTAVAIL,
        ]:
            with self.subTest(errno=code):
                self.assertTrue(is_network_startup_error(OSError(code, 'test')))

    def test_is_network_startup_error_non_network_oserror(self) -> None:
        import errno

        self.assertFalse(is_network_startup_error(OSError(errno.ENOENT, 'test')))

    def test_is_network_startup_error_non_network_exception(self) -> None:
        self.assertFalse(is_network_startup_error(RuntimeError('test')))


if __name__ == '__main__':
    unittest.main()
