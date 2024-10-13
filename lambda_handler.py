import json
import logging
from dotenv import find_dotenv, load_dotenv
import os
import requests
from langchain.agents.agent_types import AgentType
# from langchain_experimental.agents.agent_toolkits import create_csv_agent
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI
import boto3
from io import StringIO
import pandas as pd
from boto3.dynamodb.conditions import Key
import time

load_dotenv(find_dotenv())
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
SLACK_BOT_USER_ID = os.environ["SLACK_BOT_USER_ID"]
OPEN_AI_API_KEY = os.environ["OPEN_AI_API_KEY"]
SLACK_BASE_URL = "https://slack.com/api/chat.postMessage"
S3_BUCKET_NAME = 'starkslackbot'
S3_FILE_NAME = 'Learner Data.csv'
DYNAMO_DB_TABLE = "ProcessedSlackEventsId"


class LambdaHandler:
    def __init__(self) -> None:
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        self.slack_url = SLACK_BASE_URL
        self.s3 = boto3.client('s3')
        self.learner_data = pd.DataFrame()
        self.llm = ChatOpenAI(temperature=0, model='gpt-4o', api_key=OPEN_AI_API_KEY)
        self.df_agent = ""
        self.dynamodb = boto3.resource('dynamodb')
        self.dynamodb_table = self.dynamodb.Table(DYNAMO_DB_TABLE)
        self.client_msg_id = ""
        self.event_id = ""

    def handle_app_mention(self, event):
        """
            function to handle app slack mentions
        """
        body = json.loads(event["body"])
        self.load_data()
        df_agent = create_pandas_dataframe_agent(
                llm=self.llm,
                df=self.learner_data,
                # verbose=True,
                agent_type=AgentType.OPENAI_FUNCTIONS,
                allow_dangerous_code=True
            )
        self.client_msg_id = body["event"]["client_msg_id"]
        self.event_id = body["event_id"]
        # self.logger.info(f"event id {self.event_id}")
        event_status = self.get_event_status(self.event_id)

        if event_status == "done":
            # self.logger.info(
            #     f"Event {self.event_id} is already processed with status: done. Skipping."
            # )
            return
        elif event_status == "in process":
            # self.logger.info(
            #     f"Event {self.event_id} is currently being processed. Skipping."
            # )
            return
        elif event_status == "failed":
            self.logger.info(f"Event {self.event_id} previously failed. Retrying...")

        # If not processed or previously failed, set status to 'in process'
        self.mark_event_in_process(self.event_id)

        try:
            text = body["event"]["text"]
            mention = f"<@{SLACK_BOT_USER_ID}>"
            text = text.replace(mention, "").strip()
            response = df_agent.invoke(text)
            self.send_slack_response(body=body, msg=response)
            self.mark_event_as_done(self.event_id)
        except Exception as e:
            self.logger.info(f"Error occured at generating response --- {e}")
            self.mark_event_as_failed(self.event_id)

    def get_event_status(self, event_id):
        """
        Checks if the event_id is already in DynamoDB and returns its processing status.
        Returns:
            - "done" if the event is already processed.
            - "in process" if the event is being processed.
            - "failed" if the event processing previously failed.
            - None if the event does not exist.
        """
        try:
            response = self.dynamodb_table.get_item(Key={"event_id": event_id})
            if "Item" in response:
                return response["Item"][
                    "flag"
                ]  # Returns the flag (in process, done, failed)
        except Exception as e:
            self.logger.info(f"Error checking event_id {event_id} in DynamoDB: {e}")
        return None

    def mark_event_in_process(self, event_id):
        """
        Mark the event as 'in process' by storing it in DynamoDB.
        """
        try:
            ttl = int(time.time()) + 300  # Set TTL for 24 hours (optional)
            self.dynamodb_table.put_item(
                Item={"event_id": event_id, "flag": "in process", "ttl": ttl}
            )
        except Exception as e:
            self.logger.info(
                f"Error marking event {event_id} as in process in DynamoDB: {e}"
            )

    def mark_event_as_done(self, event_id):
        """
        Mark the event as 'done' after successful processing.
        """
        try:
            self.dynamodb_table.update_item(
                Key={"event_id": event_id},
                UpdateExpression="SET flag = :status",
                ExpressionAttributeValues={":status": "done"},
            )
        except Exception as e:
            self.logger.info(f"Error marking event {event_id} as done in DynamoDB: {e}")

    def mark_event_as_failed(self, event_id):
        """
        Mark the event as 'failed' if processing fails.
        """
        try:
            self.dynamodb_table.update_item(
                Key={"event_id": event_id},
                UpdateExpression="SET flag = :status",
                ExpressionAttributeValues={":status": "failed"},
            )
        except Exception as e:
            self.logger.info(
                f"Error marking event {event_id} as failed in DynamoDB: {e}"
            )

    def send_slack_response(self, body, msg):
        """curl -X POST -H 'Authorization: Bearer token' \
-H 'Content-type: application/json' \
--data '{"channel":"C07F9QNS8S0","text":"I hope the tour went well, Mr. Wonka."}' \
https://slack.com/api/chat.postMessage"""
        try:
            channel_id = body["event"]["channel"]
            # url = "https://slack.com/api/chat.postMessage"
            headers = {
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                'channel': channel_id,
                'text': msg["output"]
            }
            response = requests.post(self.slack_url, headers=headers, json=payload)
        except Exception as e:
            self.logger.info(f"Error occured at sending slack response --- {e}")

    def load_data(self):
        dtype = {
        'Learner ID': str,
        'Course Prefix': str,
        'Platform': str,
        'Course Name': str,
        'Term': str,
        'AY': str,
        'Verified': int,
        'Passed': int,
        'Credit Converted': int,
        'Grade': int
        }

        try:
            obj = self.s3.get_object(Bucket=S3_BUCKET_NAME,Key=S3_FILE_NAME)
            data = obj['Body'].read().decode('utf-8')
            self.learner_data = pd.read_csv(StringIO(data), dtype=dtype)
        except Exception as e:
            self.logger.info(f"Error at loading data from S3 --- {e}")

    # def creat_agent(self):
    #     try:
    #         self.df_agent =
    #     except Exception as e:
    #         self.logger.info(f"Error occured creating csv agent --- {e}")

    def url_verification_handler(self,slack_event, context):
        """
            Handles verification url from slack api

            Returns: 
                Challenge parameter
        """
        challenge_answer = slack_event.get("challenge")
        self.logger.info(f"url_verification_handler was called")
        return {"statusCode": 200, "body": challenge_answer}

    def log(self, txt):
        self.logger.info(f"{txt}")

def lambda_handler(event, context):
    handler = LambdaHandler()
    # handler.log(event)
    # Check if it's a URL verification event
    if "body" in event:
        slack_body = json.loads(event["body"])

        if slack_body.get("type") == "url_verification":
            return handler.url_verification_handler(slack_body, context)
        
        if slack_body.get("event", {}).get("type") == "app_mention":
            handler.handle_app_mention(event)
    else:
        return {
            'statusCode' : 400,
            'body': "no body found"
        }
    return {
        'statusCode' : 200,
    }
