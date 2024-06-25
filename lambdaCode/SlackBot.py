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
def build_chain():
  region = os.environ["AWS_REGION"]
  kendra_index_id = os.environ["KENDRA_INDEX_ID"]
  boto3_bedrock = boto3.client(
      service_name='bedrock-runtime',
      region_name=region,
  )


  llm = Bedrock(
      client=boto3_bedrock,
      region_name = region,
      model_kwargs={"max_tokens_to_sample":300,"temperature":1,"top_k":250,"top_p":0.999,"anthropic_version":"bedrock-2023-05-31"},
      model_id="anthropic.claude-v2"
  )
      
  retriever = AmazonKendraRetriever(index_id=kendra_index_id,top_k=5,region_name=region)


  prompt_template = """Human: This is a friendly conversation between a human and an AI. 
  The AI is talkative and provides specific details from its context but limits it to 240 tokens.
  If the AI does not know the answer to a question, it truthfully says it 
  does not know.

  Assistant: OK, got it, I'll be a talkative truthful AI assistant.

  Human: Here are a few documents in <documents> tags:
  <documents>
  {context}
  </documents>
  Based on the above documents, provide a detailed answer for, {question} 
  Answer "don't know" if not present in the document. 

  Assistant:
  """
  PROMPT = PromptTemplate(
      template=prompt_template, input_variables=["context", "question"]
  )

  condense_qa_template = """{chat_history}
  Human:
  Given the previous conversation and a follow up question below, rephrase the follow up question
  to be a standalone question.

  Follow Up Question: {question}
  Standalone Question:

  Assistant:"""
  standalone_question_prompt = PromptTemplate.from_template(condense_qa_template)


  
  qa = ConversationalRetrievalChain.from_llm(
        llm=llm, 
        retriever=retriever, 
        condense_question_prompt=standalone_question_prompt, 
        return_source_documents=True, 
        combine_docs_chain_kwargs={"prompt":PROMPT},
        verbose=True)

  # qa = ConversationalRetrievalChain.from_llm(llm=llm, retriever=retriever, qa_prompt=PROMPT, return_source_documents=True)
  return qa
chat_history = []
qa = build_chain()
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
	if (slack_user != "U079K9G0R7X"):
		# Replace the bot username with an empty string
		msg = call_bedrock(slack_text.replace('<@U079K9G0R7X>', ''))
	
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



def run_chain(chain, prompt: str, history=[]):
	return chain({"question": prompt, "chat_history": history})

def call_bedrock(question):
	
	result = run_chain(qa, question, chat_history)
	chat_history.append((question, result["answer"]))
	result2 = result['answer'] 
	if 'source_documents' in result:
		result2=result2+"\\n Sources:"
		for d in result['source_documents']:
			result2=result2+"\\n" + d.metadata['source']
	return result2 

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