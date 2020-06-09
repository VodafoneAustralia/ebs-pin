import sys
import logging
import botocore
import boto3
import ebspin.ec2 as ec2

class Base:
    options = None
    metadata = None
    session = None
    ec2 = None

    def __init__(self, options, metadata):
        self.options = options
        self.metadata = metadata
        self.session = boto3.Session(region_name=metadata['region'])
        self.ec2 = ec2.Ec2(self.session.client('ec2'))

    def attach(self):
        name = self.ec2.get_instance_name(self.metadata['instanceId']) or self.metadata['instanceId']
        volume_name = "%s-%s" % (name, self.options.device)
        logging.info("Volume name: %s" % volume_name)

        logging.info("Finding volume...")

        volume_id = self.ec2.get_latest_volume_id_available(self.options.uuid)
        if volume_id:
            logging.info("Volume found: %s" % volume_id)
            logging.info("Checking volume is in same availability zone as instance...")
            if self.ec2.get_volume_region(volume_id) != self.metadata['availabilityZone']:
                logging.info("Volume in another availability zone, snapshot required.")
                snapshot_id = self.ec2.create_snapshot(volume_id)
                if snapshot_id:
                    logging.info("Snapshot created: %s" % snapshot_id)
                    volume_id = None
        else:
            snapshot_id = self.ec2.get_latest_snapshot_id(self.options.uuid)
            if snapshot_id:
                logging.info("Snapshot found: %s" % snapshot_id)
            else:
                logging.info("No snapshot found. An empty #%s volume will be created of #%s GB." % (self.options.type, self.options.size))

        if not volume_id:
            logging.info("Creating volume...")
            volume_id = self.ec2.create_volume(self.options.size, self.options.type, self.metadata['availabilityZone'], snapshot_id)
            if volume_id:
                logging.info("Created volume: %s" % volume_id)

                logging.info("Tagging volume...")
                self.ec2.tag_volume(volume_id, volume_name, self.options)
                logging.info("Volume tagged.")
            else:
                logging.error("Volume failed creation.")
                sys.exit(1)

        if volume_id:
            logging.info("Attaching volume...")
            if self.ec2.attach_volume(volume_id, self.metadata['instanceId'], self.options.device):
                logging.info('Volume attached to instance.')
            else:
                logging.info('Volume attachment failed.')
                sys.exit(1)

        self.ec2.clean_old_volumes(self.options.uuid, volume_id)
        self.ec2.clean_snapshots(self.options.uuid)

    def snapshot(self):
        logging.info("Finding volumes...")
        volumes = self.ec2.get_volume_id(self.metadata['instanceId'], self.options.uuid)

        if len(volumes) > 0:
            for volume_id in volumes:
                logging.info("Creating snapshot for volume %s" % volume_id)
                response = self.ec2.create_snapshot(volume_id, self.options.tags)
                snapshot_id = response["SnapshotId"]
                snapshot_complete_waiter = self.get_waiter('snapshot_completed')
                try
                    snapshot_complete_waiter.wait(SnapshotIds=[snapshot_id])
                    if self.ec2.create_snapshot(volume_id, self.options.tags):
                        logging.info("Volume %s snapshot created." % volume_id)
                    else:
                        logging.error("Volume %s snapshot failed." % volume_id)

                except botocore.exceptions.WaiterError as e:
                    if "Max attempts exceeded" in e.message
                        logging.info("Snapshot did not complete in 600 seconds for volume %s." % volume_id)
                    else
                        logging.info("Snapshot did not complete with error %s." % e.message)
        else:
            logging.info("No volumes found")

    # TODO test this method - should work?
    def tag(self):
        logging.info("Finding volumes...")
        volumes = self.ec2.get_volume_id(self.metadata['instanceId'], self.options.uuid)

        if len(volumes) > 0:
            for volume_id in volumes:
                if self.ec2.tag_volume(volume_id, self.ec2.get_volume_name(volume_id), self.options):
                    logging.info("Volume %s tagged." % volume_id)
                else:
                    logging.error("Volume %s failed tagging." % volume_id)
        else:
            logging.info("No volumes found")