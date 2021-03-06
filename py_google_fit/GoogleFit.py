from datetime import timedelta, datetime
from typing import List

import httplib2
from apiclient.discovery import build
from oauth2client import tools
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from enum import Enum


class GFitDataType(Enum):
    WEIGHT = ('com.google.weight', float, 'fpVal')
    STEPS = ('com.google.step_count.delta', int, 'intVal')


class GoogleFit(object):
    """
    Manages the service to access your Google Fit account data.
    """

    _AUTH_SCOPES = ['https://www.googleapis.com/auth/fitness.body.read',
                    'https://www.googleapis.com/auth/fitness.activity.read',
                    'https://www.googleapis.com/auth/fitness.nutrition.read']

    def __init__(self,
                 client_id: str,
                 client_secret: str):
        """

        :param client_id: Your google client id
        :param client_secret: Your google client secret
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._service = None

    def authenticate(self,
                     auth_scopes: List[str] = _AUTH_SCOPES,
                     credentials_file: str = '.google_fit_credentials'):
        """
        Authenticate and give access to google auth scopes. If no valid credentials file is found, a browser will open
        requesting access.
        :param auth_scopes: [optional] google auth scopes: https://developers.google.com/identity/protocols/googlescopes#fitnessv1
        :param credentials_file: [optional] path to credentials file
        """
        flow = OAuth2WebServerFlow(self._client_id, self._client_secret, auth_scopes)
        storage = Storage(credentials_file)
        credentials = storage.get()

        if credentials is None or credentials.invalid:
            credentials = tools.run_flow(flow, storage)
        http = httplib2.Http()
        http = credentials.authorize(http)
        self._service = build('fitness', 'v1', http=http)

    def _execute_aggregate_request(self, data_type: str, start_date: datetime, end_date: datetime):
        def to_epoch(dt: datetime) -> int:
            return int(dt.timestamp()) * 1000

        body = {
            "aggregateBy": [{"dataTypeName": data_type}],
            "endTimeMillis": str(to_epoch(end_date)),
            "startTimeMillis": str(to_epoch(start_date)),
        }
        return self._service.users().dataset().aggregate(userId='me', body=body).execute()

    @staticmethod
    def _extract_points(resp: dict):
        return resp['bucket'][0]['dataset'][0]['point']

    @staticmethod
    def _count_total(data_type: GFitDataType, resp: dict):
        cum = 0
        points = GoogleFit._extract_points(resp)

        if len(points) == 0:
            return 'no data found'
        for _ in points:
            cum = cum + data_type.value[1](_['value'][0][data_type.value[2]])

        if data_type == GFitDataType.WEIGHT:
            return cum / len(points)
        else:
            return cum

    def _avg_for_response(self, data_type, begin, end):
        response = self._execute_aggregate_request(data_type.value[0], begin, end)
        return self._count_total(data_type, response)

    def average_today(self, data_type: GFitDataType) -> float:
        """
        :param data_type: A data type from GFitDataType
        :return: the average for the specified datatype for today up to now
        """
        begin_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_today = begin_today + timedelta(days=1)
        return self._avg_for_response(data_type, begin_today, end_today)

    def average_for_date(self, data_type: GFitDataType, dt: datetime) -> float:
        """
        This function will calculate the boundaries for the given date for you
        :param dt: A specific datetime
        :param data_type: A data type from GFitDataType
        :return: the average for the specified datatype for the given date
        """
        begin = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = begin + timedelta(days=1)
        return self._avg_for_response(data_type, begin, end)

    def rolling_daily_average(self, data_type: GFitDataType, n: int = 7) -> float:
        """
        Calculate the average over the last n days, excluding today
        :param data_type: A data type from GFitDataType
        :param n: The number of days to go back
        :return: The rolling average for the specified datatype
        """
        begin_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        begin_period = begin_today - timedelta(days=n)
        avg = self._avg_for_response(data_type, begin_period, begin_today)
        if data_type == GFitDataType.STEPS:
            return avg / n
        else:
            return avg

    def average_for_n_days_ago(self, data_type: GFitDataType, n=1) -> float:
        """
        Wrapper around `average_for_date`. This will calculate the date for you, given a number of days to go back.
        Easy function to compare the steps for a specific day in the week.
        :param data_type: A data type from GFitDataType
        :param n: The number of days to go back
        :return: the average for the specified datatype
        """
        n_days_ago = datetime.now() - timedelta(days=n)
        return self.average_for_date(data_type, n_days_ago)
