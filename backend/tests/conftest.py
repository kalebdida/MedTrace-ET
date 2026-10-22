import base64
import json
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

import app
from medtrace import gs1

GS = gs1.GS
GTIN = "09506000134352"  # GS1's example GTIN (valid check digit)

# Approximate city-centre coordinates.
ADDIS_ABABA = {"lat": 9.0108, "lon": 38.7613}
ADAMA = {"lat": 8.5400, "lon": 39.2700}
DESSIE = {"lat": 11.1300, "lon": 39.6333}


def pharma_barcode(serial="SN0001", gtin=GTIN, batch="BATCH42", expiry="301231"):
    """Raw scanner output for a serialised medicine pack."""
    return f"]d201{gtin}17{expiry}10{batch}{GS}21{serial}"


def iso(dt):
    return dt.isoformat()


def ago(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def claims_for(user="pharmacist-1", site_id=None):
    """JWT claims as the API Gateway Cognito authorizer passes them on."""
    claims = {"sub": user}
    if site_id:
        claims["custom:site_id"] = site_id
    return claims


def http_event(method, path, body=None, query=None, stage="$default", base64_body=False, claims=None):
    """API Gateway HTTP API (payload 2.0) proxy event."""
    raw = json.dumps(body) if body is not None and not isinstance(body, str) else body
    if raw is not None and base64_body:
        raw = base64.b64encode(raw.encode()).decode()
    context = {"http": {"method": method, "path": path}, "stage": stage}
    if claims is not None:
        context["authorizer"] = {"jwt": {"claims": claims, "scopes": None}}
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "queryStringParameters": query,
        "requestContext": context,
        "body": raw,
        "isBase64Encoded": base64_body,
    }


def rest_event(method, path, body=None, query=None, claims=None):
    """API Gateway REST API (payload 1.0) proxy event."""
    context = {"stage": "prod"}
    if claims is not None:
        context["authorizer"] = {"claims": claims}
    return {
        "httpMethod": method,
        "path": path,
        "queryStringParameters": query,
        "requestContext": context,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


class Context:
    aws_request_id = "test-request-id"


def call(event):
    response = app.lambda_handler(event, Context())
    body = json.loads(response["body"]) if response["body"] else None
    return response["statusCode"], body


@pytest.fixture
def aws(monkeypatch):
    """Mocked DynamoDB table + SNS topic with an SQS queue subscribed to it."""
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(name, value)

    with mock_aws():
        table = boto3.resource("dynamodb").create_table(
            TableName="medtrace-scans",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        sns = boto3.client("sns")
        topic_arn = sns.create_topic(Name="medtrace-alerts")["TopicArn"]
        sqs = boto3.client("sqs")
        queue_url = sqs.create_queue(QueueName="alert-inbox")["QueueUrl"]
        queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

        monkeypatch.setenv("SCAN_TABLE_NAME", "medtrace-scans")
        monkeypatch.setenv("ALERT_TOPIC_ARN", topic_arn)
        monkeypatch.setattr(app, "_services", None)

        def received_alerts():
            messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])
            return [json.loads(m["Body"]) for m in messages]

        yield {"table": table, "topic_arn": topic_arn, "alerts": received_alerts}

    monkeypatch.setattr(app, "_services", None)
