import datetime
import time
import plaid
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .serializers import AccessToken
from .cron import delete_transactions, fetch_transactions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from .models import Item
from .constants import *
from plaid.api import plaid_api

if PLAID_ENV == 'sandbox':
    host = plaid.Environment.Sandbox

if PLAID_ENV == 'development':
    host = plaid.Environment.Development

if PLAID_ENV == 'production':
    host = plaid.Environment.Production

configuration = plaid.Configuration(
    host=host,
    api_key={
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
        'plaidVersion': '2020-09-14'
    }
)
api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)
products = []
for product in PLAID_PRODUCTS:
    products.append(Products(product))

# Create Link token


class LinkTokenAPIView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = self.request.user
        print(PLAID_CLIENT_ID)
        print(str(user.id))
        try:
            link_token_request = LinkTokenCreateRequest(
                products=products,
                user=LinkTokenCreateRequestUser(
                    client_user_id=str(time.time())
                ),
                client_name='BRIGHT MONEY ASSIGNMENT',
                country_codes=list(
                    map(lambda x: CountryCode(x), PLAID_COUNTRY_CODES)),
                language='en',
                # webhook='https://webhook.sample.com',
            )
            if PLAID_REDIRECT_URI != None:
                request['redirect_uri'] = PLAID_REDIRECT_URI
            # link_token_response = {
            #     user: {
            #         'client_user_id': str(user.id),
            #     },
            #     'client_name': 'BRIGHT MONEY ASSIGNMENT',
            #     'country_codes': ['US'],
            #     'language': 'en',
            #     'webhook': 'https://webhook.sample.com',

            # }
            link_token_response = client.link_token_create(link_token_request)
            print(link_token_response)
            return Response(link_token_response.to_dict(), status=status.HTTP_200_OK)
        except plaid.ApiException as e:
            print(e, "PLAID_ERROR")
            return Response(e.body, status=e.status)
        except Exception as e:
            print(e, "ERROR")
            return Response("Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# exchange link token for public token


class PublicTokenAPIView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_data = request.data
        print('request_adta', request_data)
        institution_id = request_data.get('institution_id')
        print('@##@@#@@', institution_id)
        try:
            public_token_request = SandboxPublicTokenCreateRequest(
                institution_id=institution_id,
                initial_products=products,
            )
            public_token_response = client.sandbox_public_token_create(
                public_token_request)
            print(public_token_response)
            return Response(public_token_response.to_dict(), status=status.HTTP_200_OK)
        except plaid.ApiException as e:
            print(e, "PLAID_ERROR")
            return Response(e.body, status=e.status)
        except Exception as e:
            print(e, "ERROR")
            return Response("Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Exchange public token from access token
class AccessTokenAPIView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_data = request.data
        public_token = request_data.get('public_token')
        try:
            exchange_request = ItemPublicTokenExchangeRequest(
                public_token=public_token)
            exchange_response = client.item_public_token_exchange(
                exchange_request).to_dict()
            print(exchange_response)
            access_token = exchange_response['access_token']
            item = Item.objects.create(access_token=access_token,
                                       item_id=exchange_response['item_id'],
                                       user=self.request.user
                                       )
            item.save()

            # Async Task
            fetch_transactions.delay(access_token)

        except plaid.ApiException as e:
            print(e, "PLAID_ERROR")
            return Response(e.body, status=e.status)
        except Exception as e:
            print(e, "ERROR")
            return Response("Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(data={'exchange_response': exchange_response, 'request_id': request.META["X-Request-ID"]}, status=status.HTTP_200_OK)


class GetTransactionsAPI(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item = Item.objects.filter(user=self.request.user)
        if item.count() > 0:
            access_token = item.values('access_token')[0]['access_token']

            # transactions of two years i.e. 730 days
            start_date = '{:%Y-%m-%d}'.format(
                datetime.datetime.now() + datetime.timedelta(-730))
            end_date = '{:%Y-%m-%d}'.format(datetime.datetime.now())

            try:
                request = TransactionsSyncRequest(
                    access_token=access_token, start_date=start_date, end_date=end_date)
                transactions_response = client.Transactions.get(
                    access_token, start_date, end_date)
            except plaid.ApiException as e:

                return Response(e.body, status=e.status)
            except Exception as e:
                print(e, "ERROR")
                return Response("Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response(data={'request_id': request.META["X-Request-ID"], 'transactions': transactions_response}, status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': 'No item found', 'request_id': request.META["X-Request-ID"]})


class AccountInfoAPIView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        item = Item.objects.filter(user=self.request.user)
        if item.count() > 0:
            access_token = item.values('access_token')[0]['access_token']
            try:
                item_response = client.Item.get(access_token)
                institution_response = client.Institutions.get_by_id(
                    item_response['item']['institution_id'])
            except plaid.ApiException as e:

                return Response(e.body, status=e.status)
            except Exception as e:
                print(e, "ERROR")
                return Response("Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response(
                data={'request_id': request.META["X-Request-ID"], 'item': item_response['item'],
                      'institution': institution_response['institution']},
                status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED, data={'request_id': request.META["X-Request-ID"]})


@csrf_exempt
def webhook(request):
    request_data = request.data
    webhook_type = request_data.get('webhook_type')
    webhook_code = request_data.get('webhook_code')

    if webhook_type == 'TRANSACTIONS':
        item_id = request_data.get('item_id')
        if webhook_code == 'TRANSACTIONS_REMOVED':
            removed_transactions = request_data.get('removed_transactions')
            delete_transactions.delay(item_id, removed_transactions)

        else:
            new_transactions = request_data.get('new_transactions')
            fetch_transactions.delay(None, item_id, new_transactions)

    return HttpResponse('Webhook received', status=status.HTTP_202_ACCEPTED)
