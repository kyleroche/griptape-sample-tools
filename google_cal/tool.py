from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from typing import List, Dict
import os
from schema import Schema, Literal, Optional
from griptape.artifacts import ListArtifact, JsonArtifact
from griptape.tools import BaseTool
from griptape.utils.decorators import activity
import uuid
from zoomus import ZoomClient
import json
import jwt
import time

SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": os.getenv('GOOGLE_PROJECT_ID'),
    "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID'),
    "private_key": os.getenv('GOOGLE_PRIVATE_KEY'),
    "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
    "client_id": os.getenv('GOOGLE_CLIENT_ID'),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL').replace('@', '%40')}"
}

class GoogleCalendarTool(BaseTool):
    def __init__(self):
        super().__init__()
        self._init_zoom_client()

    def _init_zoom_client(self):
        if os.getenv('ZOOM_ACCOUNT_ID') and os.getenv('ZOOM_CLIENT_ID') and os.getenv('ZOOM_CLIENT_SECRET'):
            self.zoom_client = ZoomClient(
                os.getenv('ZOOM_CLIENT_ID'),  # First positional arg: api_key
                os.getenv('ZOOM_CLIENT_SECRET'),  # Second positional arg: api_secret
                os.getenv('ZOOM_ACCOUNT_ID')  # Third positional arg: api_account_id
            )
        else:
            self.zoom_client = None
            self.zoom_account_id = None

    def _get_zoom_token(self):
        """Generate Server-to-Server OAuth token for Zoom"""
        if not self.zoom_client:
            return None
            
        payload = {
            'iss': os.getenv('ZOOM_CLIENT_ID'),
            'exp': time.time() + 3600,  # Token expires in 1 hour
            'aud': 'https://zoom.us',
            'account_id': os.getenv('ZOOM_ACCOUNT_ID')
        }
        
        return jwt.encode(
            payload,
            os.getenv('ZOOM_CLIENT_SECRET'),
            algorithm='HS256'
        )

    @activity(
        config={
            "description": "Searches events in Google Calendar using service account credentials",
            "schema": Schema({
                Literal(
                    "timeMin",
                    description="Start time in ISO format (e.g. 2024-03-20T00:00:00Z)"
                ): str,
                Literal(
                    "timeMax",
                    description="End time in ISO format (e.g. 2024-03-21T00:00:00Z)"
                ): str,
                Literal(
                    "maxResults",
                    description="Maximum number of events to return"
                ): int,
                Literal(
                    "q",
                    description="Free text search terms to find events that match"
                ): str
            })
        }
    )
    def search_calendar(self, params: dict) -> ListArtifact:
        """Searches Google Calendar events within specified parameters."""
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
        
        service = build('calendar', 'v3', credentials=delegated_credentials)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=params["values"]["timeMin"],
            timeMax=params["values"]["timeMax"],
            maxResults=params["values"]["maxResults"],
            q=params["values"]["q"],
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        calendar_events = []
        
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            event_data = {
                'id': event['id'],
                'summary': event.get('summary', 'No title'),
                'start': start,
                'end': end,
                'location': event.get('location', ''),
                'description': event.get('description', ''),
                'attendees': [
                    attendee.get('email') 
                    for attendee in event.get('attendees', [])
                ]
            }
            calendar_events.append(JsonArtifact(event_data))
            
        return ListArtifact(calendar_events)

    @activity(
        config={
            "description": "Creates a new calendar event with optional attendees and video conferencing",
            "schema": Schema({
                Literal(
                    "summary",
                    description="Title of the event"
                ): str,
                Literal(
                    "start",
                    description="Start time in ISO format"
                ): str,
                Literal(
                    "end",
                    description="End time in ISO format"
                ): str,
                Optional(Literal(
                    "description",
                    description="Description of the event"
                )): str,
                Optional(Literal(
                    "attendees",
                    description="List of attendee email addresses"
                )): [str],
                Optional(Literal(
                    "location",
                    description="Location of the event"
                )): str,
                Optional(Literal(
                    "conference_type",
                    description="Type of video conference to add ('meet' or 'zoom')"
                )): str,
                Optional(Literal(
                    "send_notifications",
                    description="Whether to send email notifications to attendees"
                )): bool
            })
        }
    )
    def create_event(self, params: dict) -> JsonArtifact:
        """Creates a new calendar event with optional attendees and video conferencing."""
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/calendar.events']
        )
        
        delegated_credentials = credentials.with_subject(os.getenv('GOOGLE_DELEGATED_EMAIL'))
        service = build('calendar', 'v3', credentials=delegated_credentials)

        event_body = {
            'summary': params["values"]["summary"],
            'start': {'dateTime': params["values"]["start"]},
            'end': {'dateTime': params["values"]["end"]},
        }

        if params["values"].get("description"):
            event_body['description'] = params["values"]["description"]
            
        if params["values"].get("location"):
            event_body['location'] = params["values"]["location"]
            
        if params["values"].get("attendees"):
            event_body['attendees'] = [{'email': email} for email in params["values"]["attendees"]]
            
        conference_type = params["values"].get("conference_type")
        if conference_type:
            if conference_type.lower() == 'meet':
                event_body['conferenceData'] = {
                    'createRequest': {
                        'requestId': f"{uuid.uuid4().hex}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                }
            elif conference_type.lower() == 'zoom' and self.zoom_client:
                # Create Zoom meeting with Server-to-Server OAuth
                token = self._get_zoom_token()
                self.zoom_client.config['token'] = token
                
                zoom_meeting = self.zoom_client.meeting.create(
                    user_id=os.getenv('ZOOM_USER_ID'),
                    topic=params["values"]["summary"],
                    type=2,  # Scheduled meeting
                    start_time=params["values"]["start"],
                    duration=(
                        datetime.fromisoformat(params["values"]["end"].replace('Z', '+00:00')) -
                        datetime.fromisoformat(params["values"]["start"].replace('Z', '+00:00'))
                    ).seconds // 60,
                    timezone='UTC',
                    settings={
                        'join_before_host': True,
                        'waiting_room': False
                    }
                )
                
                meeting_data = json.loads(zoom_meeting.content)
                
                # Add Zoom meeting details to event
                event_body['description'] = (
                    f"{event_body.get('description', '')}\n\n"
                    f"Zoom Meeting Link: {meeting_data['join_url']}\n"
                    f"Meeting ID: {meeting_data['id']}\n"
                )
                event_body['location'] = meeting_data['join_url']

        event = service.events().insert(
            calendarId='primary',
            body=event_body,
            conferenceDataVersion=1 if conference_type == 'meet' else 0,
            sendUpdates='all' if params["values"].get("send_notifications") else 'none'
        ).execute()

        response_data = {
            'id': event['id'],
            'htmlLink': event['htmlLink'],
            'attendees': event.get('attendees'),
            'status': event['status']
        }
        
        if conference_type == 'meet':
            response_data['conferenceData'] = event.get('conferenceData')
        elif conference_type == 'zoom' and 'location' in event_body:
            response_data['zoomLink'] = event_body['location']

        return JsonArtifact(response_data)

def init_tool() -> BaseTool:
    return GoogleCalendarTool() 