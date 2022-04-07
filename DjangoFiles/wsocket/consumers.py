# chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging

from AuthBillet.models import TibilletUser

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user :TibilletUser = self.scope["user"]
        # import ipdb; ipdb.set_trace()
        if self.user.is_anonymous:
            logger.warning(f"WEBSOCKET connect {self.user}")
            await self.close()

        logger.info(f'ChatConsumer : {self.user}')

        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'chat_%s' % self.room_name

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get('message')
        if message:
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message
                }
            )

    # Receive message from room group
    async def chat_message(self, event):
        message = event.get('message')
        if message:
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
                'message': message
            }))
