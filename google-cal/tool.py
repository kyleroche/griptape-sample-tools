from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from typing import List, Dict
import os
from schema import Schema, Literal
from griptape.artifacts import ListArtifact, JsonArtifact
from griptape.tools import BaseTool
from griptape.utils.decorators import activity

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

def init_tool() -> BaseTool:
    return GoogleCalendarTool() 