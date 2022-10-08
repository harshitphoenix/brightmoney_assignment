import datetime
import plaid
# from plaid.model.link_token_create_request import LinkTokenCreateRequest
# from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
# from plaid.model.products import Products
# from plaid.model.country_code import CountryCode
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

client = plaid.Client(client_id=PLAID_CLIENT_ID, secret=PLAID_SECRET,
                      public_key=PLAID_PUBLIC_KEY, environment=PLAID_ENV, api_version='2020-09-14')

# class LinkTokenAPIView(APIView):
#     authentication_classes = (TokenAuthentication,)
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         user = self.request.user
#         print(PLAID_CLIENT_ID)
#         print(user.id)
#         # link_token_request = LinkTokenCreateRequest(
#         #     user=LinkTokenCreateRequestUser(
#         #         client_user_id=str(user.id),
#         #     ),
#         #     client_name='BRIGHT MONEY ASSIGNMENT',
#         #     products=[Products.TRANSACTIONS],
#         #     country_codes=[CountryCode.US],
#         #     language='en',
#         #     webhook='https://webhook.sample.com',

#         # )
#         link_token_response = {
#             user: {
#                 'client_user_id': str(user.id),
#             },
#             'client_name': 'BRIGHT MONEY ASSIGNMENT',
#             'country_codes': ['US'],
#             'language': 'en',
#             'webhook': 'https://webhook.sample.com',

#         }
#         link_token_response = client.Link.create(link_token_request)
#         return Response(link_token_response.to_dict(), status=status.HTTP_200_OK)


class AccessTokenAPIView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_data = request.POST
        public_token = request_data.get('public_token')
        try:
            exchange_response = client.Item.public_token.exchange(public_token)
            serializer = AccessToken(data=exchange_response)
            if serializer.is_valid():
                access_token = serializer.validated_data['access_token']
                item = Item.objects.create(access_token=access_token,
                                           item_id=serializer.validated_data['item_id'],
                                           user=self.request.user
                                           )
                item.save()

                # Async Task
                fetch_transactions.delay(access_token)

        except plaid.errors.PlaidError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': e.display_message, 'request_id': request.META["X-Request-ID"]})

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
                transactions_response = client.Transactions.get(
                    access_token, start_date, end_date)
            except plaid.errors.PlaidError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST)

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
            except plaid.errors.PlaidError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            return Response(
                data={'request_id': request.META["X-Request-ID"], 'item': item_response['item'],
                      'institution': institution_response['institution']},
                status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED, data={'request_id': request.META["X-Request-ID"]})


@csrf_exempt
def webhook(request):
    request_data = request.POST
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
