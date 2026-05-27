from routemq.controller import Controller


class ExampleController(Controller):
    @staticmethod
    async def handle_message(device_id: str, payload, client):
        print(f'Received message for device {device_id}')
        print(f'Payload: {payload}')
        # Process the message here
        return {'status': 'success', 'device_id': device_id}
