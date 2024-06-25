## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0

import json
import os
import boto3
import urllib3
from langchain.retrievers import AmazonKendraRetriever
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain.llms.bedrock import Bedrock
from langchain.chains.llm import LLMChain
from botocore.response import StreamingBody

# Initialize AWS clients for Bedrock and Secrets Manager
bedrock_runtime_client = boto3.client('bedrock-runtime')
secretsmanager_client = boto3.client('secretsmanager')

# Set the Slack API URL and fetch the Slack token from Secrets Manager
SLACK_URL = 'https://slack.com/api/chat.postMessage'
slack_token = json.loads(
	secretsmanager_client.get_secret_value(
		SecretId=os.environ.get('token')
	)['SecretString']
)['token'] 
http = urllib3.PoolManager()

def handle_challenge(event):
	"""
	Handles the Slack challenge event for verifying the URL.
	https://api.slack.com/events/url_verification

	Args:
		event (dict): The event data from the Slack challenge.

	Returns:
		dict: A response dictionary with the status code and the challenge value.
	"""
	body = json.loads(event['body'])

	return {
		'statusCode': 200,
		'body': body['challenge']
	}

def handle_message(event):
	"""
	Handles the Slack message event and calls the Bedrock AI model.

	Args:
		event (dict): The event data from the Slack message.

	Returns:
		dict: A response dictionary with the status code and a message.
	"""
	slack_body = json.loads(event['body'])
	slack_text = slack_body.get('event').get('text')
	slack_user = slack_body.get('event').get('user')
	channel = slack_body.get('event').get('channel')
	if (slack_user != "U06D5B8AR8R"):
		# Replace the bot username with an empty string
		msg = call_bedrock(slack_text.replace('<@U06D5B8AR8R>', ''))
	
		# Prepare the data for the Slack API request
		data = {
			'channel': channel,
			'text': f"<@{slack_user}> {msg}"
		}
	
		headers = {
			'Authorization': f'Bearer {slack_token}',
			'Content-Type': 'application/json',
		}

		# Send the message to the Slack API
		http.request(
			'POST',
			SLACK_URL,
			headers=headers,
			body=json.dumps(data)
		)

	return {
		'statusCode': 200,
		'body': json.dumps({'msg': "message recevied"})
	}

def call_bedrock(question):
	"""
	Calls the Bedrock AI model with the given question.

	Args:
		question (str): The question to ask the Bedrock AI model.

	Returns:
		str: The response from the Bedrock AI model.
	"""
	body = json.dumps({
		"prompt": f"\\n\\nHuman: Act as a slack bot. {question}\\n\\nAssistant:",
		"maxTokens": 3000,
		"temperature": 0.5,
		"topP": 1
	})

	model_id = 'ai21.j2-ultra-v1'
	accept = 'application/json'
	content_type = 'application/json'

	# Call the Bedrock AI model
	response = bedrock_runtime_client.invoke_model(
		body=body,
		modelId=model_id,
		accept=accept,
		contentType=content_type
	)

	# Process the response from the Bedrock AI model
	if isinstance(response.get('body'), StreamingBody):
		response_content = response['body'].read().decode('utf-8')
	else:
		response_content = response.get('body')

	response_body = json.loads(response_content)

	return response_body.get('completions')[0].get('data').get('text')

def handler(event, context):
	"""
	The main Lambda handler function.

	Args:
		event (dict): The event data from the Slack API.
		context (dict): The Lambda context object.

	Returns:
		dict: The response dictionary based on the event type.
	"""
	# Respond to the Slack Challenge if presented, otherwise handle the Bedrock interaction
	event_body = json.loads(event.get("body"))
	response = None
	if event_body.get("type") == "url_verification":
		response = handle_challenge(event)
	else:
		response = handle_message(event)

	return response