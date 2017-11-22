from datetime import datetime,timezone
import sys
import boto3
import json


def pipeline_event(event, context):

    state = get_final_state(event)
    if state is None:
        return

    event_time = datetime.strptime(event['time'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    metric_data = []

    if event['detail-type'] == "CodePipeline Pipeline Execution State Change":
        # Write green/red time based on last execution state
        prior_execution = get_prior_execution(event['detail']['pipeline'], event['detail']['execution-id'])
        if prior_execution is not None:
            last_execution_state = prior_execution['status']
            seconds_since_last_execution = (event_time - prior_execution['lastUpdateTime']).total_seconds()
            if last_execution_state == "Succeeded":
                append_metric(metric_data, "GreenTime", event, seconds=seconds_since_last_execution)
            elif last_execution_state == "Failed":
                append_metric(metric_data, "RedTime", event, seconds=seconds_since_last_execution)

        if state == "SUCCEEDED":
            append_metric(metric_data, "SuccessCount", event, count=1)

            current_execution = get_execution(event['detail']['pipeline'], event['detail']['execution-id'])
            if current_execution is not None:
                duration = (event_time - current_execution['startTime']).total_seconds()
                append_metric(metric_data, "LeadTime", event, seconds=duration)
        elif state == "FAILED":
            append_metric(metric_data, "FailureCount", event, count=1)

    elif event['detail-type'] == "CodePipeline Stage Execution State Change":
        if state == "SUCCEEDED":
            append_metric(metric_data, "SuccessCount", event, count=1)
            #append_metric(metric_data, "LeadTime", event, seconds=duration)
        elif state == "FAILED":
            append_metric(metric_data, "FailureCount", event, count=1)

    elif event['detail-type'] == "CodePipeline Action Execution State Change":
        if state == "SUCCEEDED":
            append_metric(metric_data, "SuccessCount", event, count=1)

            #if event['detail']['category'] == "Approval":
            #    append_metric(metric_data, "WaitTime", event, seconds=duration)
            #else:
            #    append_metric(metric_data, "LeadTime", event, seconds=duration)
        elif state == "FAILED":
            append_metric(metric_data, "FailureCount", event, count=1)

    if len(metric_data) > 0:
        client = boto3.client('cloudwatch')
        client.put_metric_data(
            Namespace='Pipeline',
            MetricData=metric_data
        )


# Return the state from the event iff it's one of SUCCEEDED or FAILED
def get_final_state(event):
    if 'detail' in event and 'state' in event['detail']:
        if any(event['detail']['state'] in s for s in ['SUCCEEDED', 'FAILED']):
            return event['detail']['state']
    return None


# Return the execution summary for a given execution id
def get_execution(pipeline_name, execution_id):
    client = boto3.client('codepipeline')
    response = client.list_pipeline_executions(pipelineName=pipeline_name)
    for e in response['pipelineExecutionSummaries']:
        if e['pipelineExecutionId'] == execution_id:
            return e

    return None


# Return the execution summary for the most prior final execution before a given execution id
def get_prior_execution(pipeline_name, execution_id):
    client = boto3.client('codepipeline')
    response = client.list_pipeline_executions(pipelineName=pipeline_name)
    found_current = False
    for e in response['pipelineExecutionSummaries']:
        if found_current and any(e['status'] in s for s in ['Succeeded', 'Failed']):
                return e
        elif e['pipelineExecutionId'] == execution_id:
            found_current = True

    return None


def append_metric(metric_list, metric_name, event, seconds=0, count=0):
    data = {
        'MetricName': metric_name,
        'Dimensions': [],
        'Timestamp': datetime.strptime(event['time'], '%Y-%m-%dT%H:%M:%SZ'),
    }

    resource_parts = []
    if 'pipeline' in event['detail']:
        data['Dimensions'].append({
            'Name': 'PipelineName',
            'Value': event['detail']['pipeline']
        })
        resource_parts.append(event['detail']['pipeline'])

    if 'stage' in event['detail']:
        data['Dimensions'].append({
            'Name': 'StageName',
            'Value': event['detail']['stage']
        })
        resource_parts.append(event['detail']['stage'])

    if 'action' in event['detail']:
        data['Dimensions'].append({
            'Name': 'ActionName',
            'Value': event['detail']['action']
        })
        resource_parts.append(event['detail']['action'])

    if seconds > 0:
        data['Value'] = seconds
        data['Unit'] = 'Seconds'
    elif count > 0:
        data['Value'] = count
        data['Unit'] = 'Count'
    else:
        # no metric to add
        return

    print("resource=%s metric=%s value=%s" % ('.'.join(resource_parts), metric_name, data['Value']))

    metric_list.append(data)


def generate_dashboard(client):
    paginator = client.get_paginator('list_metrics')

    response_iterator = paginator.paginate(
        Namespace='Pipeline'
    )

    pipeline_names = set()
    for response in response_iterator:
        for metric in response['Metrics']:
            for dim in metric['Dimensions']:
                if dim['Name'] == 'PipelineName':
                    pipeline_names.add(dim['Value'])


    widgets = []
    dashboard = {
        "widgets": widgets
    }
    y = 0
    for pipeline_name in sorted(pipeline_names):
        widgets.append({
            "type": "metric",
            "x": 0,
            "y": y,
            "width": 18,
            "height": 3,
            "properties": {
                "view": "singleValue",
                "metrics": [
                    [ "Pipeline", "SuccessCount", "PipelineName", pipeline_name, { "stat": "Sum", "period": 2592000 } ],
                    [ ".", "FailureCount", ".", ".", { "stat": "Sum", "period": 2592000 } ],
                    [ ".", "LeadTime", ".", ".", { "period": 2592000, "color": "#9467bd" } ],
                    [ ".", "RedTime", ".", ".", { "stat": "Sum", "period": 2592000, "yAxis": "left", "color": "#d62728" } ],
                    [ ".", "GreenTime", ".", ".", { "period": 2592000, "stat": "Sum", "color": "#2ca02c" } ]
                ],
                "region": "us-east-1",
                "title": pipeline_name,
                "period": 300
            }
        })
        y += 3

    widgets.append({
        "type": "text",
        "x": 18,
        "y": 0,
        "width": 6,
        "height": 6,
        "properties": {
            "markdown": "\nAll metrics are calculated over the past 30 days\n\n* **SuccessCount** - count of all successful pipeline executions\n* **FailureCount** - count of all failed pipeline executions\n* **LeadTime** - average pipeline time for successful executions\n* **RedTime** - sum of all time spent with a red pipeline\n* **GreenTime** - sum of all time spent with a green pipeline\n"
        }
    })

    return dashboard


def dashboard_event(event, context):
    client = boto3.client('cloudwatch')
    dashboard = generate_dashboard(client)
    client.put_dashboard(
        DashboardName='Pipeline',
        DashboardBody=json.dumps(dashboard)
    )


if __name__ == '__main__':
    dashboard_event(None, None)

