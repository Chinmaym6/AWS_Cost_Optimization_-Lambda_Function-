#This is a Python script for an AWS Lambda function that deletes old snapshots in an AWS account.
#Delete snapshots older than 30 days if:

  #The snapshot is not attached to any EBS volume
  #The snapshot is attached to an EBS volume, but that volume is not attached to any running EC2 instance
  #Keep snapshots if:

  #The snapshot is attached to an EBS volume that is currently attached to an EC2 instance
  #The snapshot is less than 30 days old
  
  
#The script uses the Boto3 library to interact with AWS services.
#This can be run manually or scheduled using AWS CloudWatch Events.

#We can delete snapshots or can move them to S3 Glacier for cost optimization.

#Usage:
#1. Create a Lambda function in AWS Management Console.
#2. Upload this script to the Lambda function.
#3. Set the retention period in days.
#4. Set the schedule for the Lambda function in AWS CloudWatch Events.
#5. Test the Lambda function by invoking it manually.
#6. Give the Lambda function the necessary permissions to access EC2 and delete snapshots.
    #ec2:DescribeSnapshots
    #ec2:DescribeVolumes
    #ec2:DeleteSnapshot
    #ec2:DeleteSnapshot

                       #OR

#Use the CloudFormation template provided in the same folder template.yaml

import boto3
from datetime import datetime, timezone
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Retention period (in days)
RETENTION_DAYS = 15  # Change this to your desired retention period

def lambda_handler(event, context):
    ec2 = boto3.client('ec2', region_name='us-east-1')  # Change region if needed
    logger.info(f"Running in region: {ec2.meta.region_name}")
    logger.info(f"Starting snapshot cleanup: Retention = {RETENTION_DAYS} days")

    try:
        paginator = ec2.get_paginator('describe_snapshots')
        pages = paginator.paginate(OwnerIds=['self'])

        total_snapshots = 0
        deleted_count = 0

        for page in pages:
            for snapshot in page['Snapshots']:
                total_snapshots += 1
                snapshot_id = snapshot['SnapshotId']
                start_time = snapshot['StartTime']
                age_days = (datetime.now(timezone.utc) - start_time).days
                logger.info(f"Snapshot {snapshot_id} is {age_days} days old")

                if age_days < RETENTION_DAYS:
                    logger.info(f"Keeping snapshot: {snapshot_id} (age {age_days} days)")
                    continue  # Keep if less than retention days

                # Step 1: Try to get volume ID from snapshot
                volume_id = snapshot.get('VolumeId')
                if not volume_id:
                    # No volume associated → Safe to delete
                    ec2.delete_snapshot(SnapshotId=snapshot_id)
                    logger.info(f"Deleted snapshot (no volume): {snapshot_id}")
                    deleted_count += 1
                    continue

                # Step 2: Check if the volume exists and is attached to a running instance
                try:
                    volume = ec2.describe_volumes(VolumeIds=[volume_id])['Volumes'][0]
                    attachments = volume.get('Attachments', [])

                    attached_to_running_instance = False
                    for attachment in attachments:
                        instance_id = attachment.get('InstanceId')
                        if instance_id:
                            instance = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]
                            state = instance.get('State', {}).get('Name')
                            if state == 'running':
                                attached_to_running_instance = True
                                break

                    if attached_to_running_instance:
                        logger.info(f"Keeping snapshot {snapshot_id} (volume attached to running instance)")
                        continue
                    else:
                        ec2.delete_snapshot(SnapshotId=snapshot_id)
                        logger.info(f"Deleted snapshot: {snapshot_id} (volume not in use)")
                        deleted_count += 1

                except ec2.exceptions.ClientError as e:
                    # If volume not found or any issue → safe to delete
                    logger.warning(f"Could not describe volume {volume_id} for snapshot {snapshot_id}. Error: {str(e)}")
                    ec2.delete_snapshot(SnapshotId=snapshot_id)
                    logger.info(f"Deleted snapshot: {snapshot_id} (volume not found)")
                    deleted_count += 1

        logger.info(f"Processed {total_snapshots} snapshots. Deleted: {deleted_count}")
        return {
            'statusCode': 200,
            'body': f"Snapshot cleanup completed. Processed: {total_snapshots}, Deleted: {deleted_count}"
        }

    except Exception as e:
        logger.error(f"Snapshot cleanup failed: {str(e)}")
        raise e
