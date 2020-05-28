import logging
import backoff
import botocore


class Ec2:
    session = None
    client = None

    def __init__(self, client):
        self.client = client

    def get_latest_volume_id_available(self, uuid):
        filters = [
                {"Name": 'tag-key',   "Values": ['UUID']},
                {"Name": 'tag-value', "Values": [uuid]}
            ]
        volumes = self.client.describe_volumes(Filters=filters)['Volumes']
        volumes = sorted(volumes, key=lambda ss: ss['CreateTime'])
        if len(volumes) == 0:
            logging.info("No volume found")
            return None
        volume = volumes.pop()
        logging.info("Volume state is {}".format(volume['State']))
        return volume['VolumeId']

    def get_latest_snapshot_id(self, uuid):
        filters = [
                {'Name': 'tag-key',   'Values': ['UUID']},
                {'Name': 'tag-value', 'Values': [uuid]},
                {'Name': 'status',    'Values': ['completed']}
            ]

        snapshots = self.client.describe_snapshots(Filters=filters)['Snapshots']
        if len(snapshots) == 0:
            return None
        snapshot = sorted(snapshots, key=lambda ss: ss['StartTime']).pop()
        return snapshot['SnapshotId']

    def get_instance_name(self, instance_id):
        filters = [
                {"Name": 'resource-id', "Values": [instance_id]},
                {"Name": 'key',         "Values": ['Name']}
            ]

        try:
            result = self.client.describe_tags(Filters=filters)['Tags'][0]['Value']
            return result
        except IndexError:
            return None

    def get_volume_id(self, instance_id, uuid):
        filters = [
                {'Name': 'attachment.instance-id', 'Values': [instance_id]},
                {'Name': 'tag:UUID', 'Values': [uuid]},
            ]

        result = self.client.describe_volumes(Filters=filters)
        # return a list of volume_ids
        volumes = [v['VolumeId'] for v in result['Volumes']]
        if len(volumes) == 0:
            return None

    def get_volume_name(self, volume_id):
        attachment = self.client.describe_volumes(VolumeIds=[volume_id])['Volumes'][0]['Attachments'][0]
        instance_name = self.get_instance_name(attachment['InstanceId'])

        return "%s-%s" % (instance_name, attachment['Device'])

    def get_volume_region(self, volume_id):
        try:
            return self.client.describe_volumes(VolumeIds=[volume_id])['Volumes'][0]['AvailabilityZone']
        except (KeyError, IndexError):
            return None

    def create_volume(self, size, volume_type, availability_zone, snapshot_id=None):
        if snapshot_id:
            response = self.client.create_volume(
                Size=size,
                SnapshotId=snapshot_id,
                AvailabilityZone=availability_zone,
                VolumeType=volume_type
            )
        else:
            response = self.client.create_volume(
                Size=size,
                AvailabilityZone=availability_zone,
                VolumeType=volume_type
            )
        volume_id = response['VolumeId']

        waiter = self.client.get_waiter('volume_available')
        waiter.wait(
            VolumeIds=[volume_id]
        )
        return response['VolumeId']

    def create_snapshot(self, volume_id, extra_tags=None):
        snapshot_id = self.client.create_snapshot(VolumeId=volume_id)['SnapshotId']
        tags = self.client.describe_volumes(VolumeIds=[volume_id])['Volumes'][0]['Tags']

        if extra_tags:
            for key, value in extra_tags.items():
                tags.append({'Key': key, 'Value': value})

        self.tag_snapshot(snapshot_id, tags)

        waiter = self.client.get_waiter('snapshot_completed')
        waiter.wait(
            Filters=[
                {
                    'Name': 'status',
                    'Values': [
                        'completed'
                    ]
                }
            ],
            SnapshotIds=[snapshot_id]
        )
        return snapshot_id

    def tag_volume(self, volume_id, volume_name, options):
        tags = [
                {'Key': 'Name',         'Value': volume_name},
                {'Key': 'UUID',         'Value': options.uuid}
            ]

        tags = [x for x in tags if x['Value'] is not None]

        # Add the tags provided from the command line
        for key, value in options.tags.items():
            tags.append({'Key': key, 'Value': value})

        return self.client.create_tags(
                Resources=[volume_id],
                Tags=tags
            )

    def tag_snapshot(self, snapshot_id, tags):
        return self.client.create_tags(
            Resources=[snapshot_id],
            Tags=tags
        )

    def attach_volume(self, volume_id, instance_id, device):
        waiter = self.client.get_waiter('volume_available')
        waiter.wait(
            VolumeIds=[volume_id]
        )

        logging.info('Volume is ready, attaching...')
        self.client.attach_volume(
            VolumeId=volume_id,
            InstanceId=instance_id,
            Device=device
        )

        waiter = self.client.get_waiter('volume_in_use')
        waiter.wait(
            Filters=[
                {
                    'Name': 'attachment.status',
                    'Values': [
                        'attached'
                    ]
                },
                {
                    'Name': 'attachment.instance-id',
                    'Values': [
                        instance_id
                    ]
                }
            ],
            VolumeIds=[volume_id]
        )
        return volume_id

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def clean_old_volumes(self, uuid, volume_id):
        """Delete all volumes matching UUID, except the one currently attached"""

        logging.info("Deleting old volumes...")
        filters = [
                {"Name": 'tag-key',   "Values": ['UUID']},
                {"Name": 'tag-value', "Values": [uuid]}
            ]
        volumes = self.client.describe_volumes(Filters=filters)['Volumes']
        old_volumes = [x for x in volumes if x['VolumeId'] != volume_id]
        if len(old_volumes) > 0:
            for volume in old_volumes:
                logging.info("Deleting volume {}...".format(volume['VolumeId']))
                try:
                    self.client.delete_volume(VolumeId=volume['VolumeId'])
                except botocore.exceptions.ClientError as e:
                    logging.critical('Failed to delete volume {}, error: {}'.format(volume['VolumeId'], e.response))
            logging.info("Old volumes deleted.")
        else:
            logging.info("No old volumes detected.")

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def clean_snapshots(self, uuid, extra_tags={}):
        """Delete all snapshots matching UUID"""

        logging.info("Deleting snapshots...")
        filters = [
            {'Name': 'tag-key',   'Values': ['UUID']},
            {'Name': 'tag-value', 'Values': [uuid]}
        ]
        snapshots = self.client.describe_snapshots(Filters=filters)['Snapshots']
        if len(snapshots) > 0:
            for snapshot in snapshots:
                tag_keys = [x["Key"] for x in snapshot['Tags']]
                if tag_keys == ["UUID", "Name"] + [x for x in extra_tags]:  # if the snapshot has extra tags, it's probably managed outside of this script and we shouldn't touch it
                    logging.info("Deleting snapshot {}...".format(snapshot['SnapshotId']))
                    try:
                        self.client.delete_snapshot(
                            SnapshotId=snapshot['SnapshotId']
                        )
                    except botocore.exceptions.ClientError as e:
                        logging.critical('Failed to delete snapshot {}, error: {}'.format(snapshot['SnapshotId'], e.response))
                else:
                    logging.info("Snapshot {} had additional unknown tags, skipping.".format(snapshot['SnapshotId']))
            logging.info("Snapshots deleted.")
        else:
            logging.info("No snapshots detected.")
