// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Stack, StackProps, Duration, CfnOutput, SecretValue, RemovalPolicy } from "aws-cdk-lib";
import { HttpApi, HttpMethod, CfnStage } from "aws-cdk-lib/aws-apigatewayv2";
import { HttpLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import { Role, ServicePrincipal, Effect, PolicyStatement, ManagedPolicy } from "aws-cdk-lib/aws-iam";
import { Runtime, Function, Code, Tracing, LayerVersion, Architecture } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";


export interface SlackBotStackProps extends StackProps {
	logRetention?: RetentionDays;
}

export class SlackBotStack extends Stack {
	constructor(scope: Construct, id: string, props: SlackBotStackProps) {
		super(scope, id, props);

		const logRetention = props.logRetention ?? RetentionDays.TWO_YEARS;
		const temporarySlackBotTokenValue = "xoxb-1234-5678-foo";

		const slackBotToken = new Secret(this, "SlackBotToken", {
			secretObjectValue: {
				token: SecretValue.unsafePlainText(temporarySlackBotTokenValue),
			},
		});

		new CfnOutput(this, "SlackBotTokenOutput", {
			value: `https://${this.region}.console.aws.amazon.com/secretsmanager/secret?name=${slackBotToken.secretName}&region=${this.region}`,
			description: "The Secret containing the Slack Bot Token.",
		});

		const lambdaRole = new Role(this, "SlackBotRole", {
			assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
			description: "Role for Slack bot lambda",
		});
		lambdaRole.addToPolicy(
			new PolicyStatement({
				effect: Effect.ALLOW,
				actions: ["bedrock:InvokeModel"],
				resources: ["*"],
			}),
		);
		lambdaRole.addManagedPolicy(ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole"));
		slackBotToken.grantRead(lambdaRole);

		NagSuppressions.addResourceSuppressions(
			lambdaRole,
			[
				{
					// The IAM user, role, or group uses AWS managed policies.
					id: "AwsSolutions-IAM4",
					reason: "Managed policies are used to simplify the solution.",
					appliesTo: ["Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"],
				},
				{
					// The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression with evidence for those permission.
					id: "AwsSolutions-IAM5",
					reason: "The role will have access to invoke all models preferred by end user.",
					appliesTo: ["Resource::*"],
				},
			],
			true,
		);
		const llmLayer = new LayerVersion(this, 'llmLayer', {
		      layerVersionName: 'llmLayer-v1',
		      compatibleRuntimes: [Runtime.PYTHON_3_12],
		      code: Code.fromAsset('llmLayer'),
		      description: 'LangChain, Boto3, Numpy',
		      removalPolicy: RemovalPolicy.DESTROY,
		      compatibleArchitectures: [Architecture.X86_64]
		});

		const lambdaLogGroup = new LogGroup(this, "SlackBotLambdaLog", {
			retention: logRetention,
		});

		const lambda = new Function(this, "SlackBotLambda", {
			code: Code.fromAsset('lambdaCode'),
			functionName: 'SlackBotLambda',
			architecture: Architecture.X86_64,
			runtime: Runtime.PYTHON_3_12,
			handler: "SlackBot.handler",
			timeout: Duration.minutes(3),
			description: "Handles Slack bot actions",
			role: lambdaRole,
			layers: [llmLayer],
    		memorySize: 256,
			environment: {
				token: slackBotToken.secretArn,
			},
			tracing: Tracing.ACTIVE,
			logGroup: lambdaLogGroup,
		});

		NagSuppressions.addResourceSuppressions(lambda, [
			{
				// The non-container Lambda function is not configured to use the latest runtime version.
				id: "AwsSolutions-L1",
				reason: "The runtime is pinned for stability.",
			},
		]);

		const slackEndpoint = new HttpApi(this, "SlackBotEndpoint", {
			description: "Proxy for Bedrock Slack bot backend.",
		});

		new CfnOutput(this, "SlackBotEndpointOutput", {
			value: slackEndpoint.url!,
			description: "The URL used to verify the Slack app.",
		});

		const apiGatewayLogGroup = new LogGroup(this, "SlackBotApiAccessLog", {
			retention: logRetention,
		});
		const defaultStage = slackEndpoint.defaultStage?.node.defaultChild as CfnStage;
		defaultStage.accessLogSettings = {
			destinationArn: apiGatewayLogGroup.logGroupArn,
			format: JSON.stringify({
				requestId: "$context.requestId",
				ip: "$context.identity.sourceIp",
				requestTime: "$context.requestTime",
				httpMethod: "$context.httpMethod",
				routeKey: "$context.routeKey",
				status: "$context.status",
				protocol: "$context.protocol",
				responseLength: "$context.responseLength",
				userAgent: "$context.identity.userAgent",
			}),
		};

		slackEndpoint.addRoutes({
			path: "/",
			methods: [HttpMethod.ANY],
			integration: new HttpLambdaIntegration("BotHandlerIntegration", lambda),
		});
	}
}
