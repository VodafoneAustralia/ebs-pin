#!/usr/bin/env python3
from ebspin import ec2
from ebspin import base
import boto3
from botocore.stub import Stubber, ANY
import botocore.exceptions
import unittest
from unittest.mock import Mock, patch
import logging
import datetime

class get_latest_volume_id_available_test(unittest.TestCase):

    def test_can_get_latest_volume_id(self):
        """Returns latest volume even if it is in-use"""

        client = boto3.client('ec2')
        stubber = Stubber(client)
        response = {"Volumes": [
            {"CreateTime": datetime.datetime.now(), "State": "available", "VolumeId": "old"},
            {"CreateTime": datetime.datetime.now() + datetime.timedelta(days=1), "State": "available", "VolumeId": "new"},
            {"CreateTime": datetime.datetime.now() + datetime.timedelta(days=2), "State": "in-use", "VolumeId": "newest"}
        ]}
        params = {'Filters': ANY}
        stubber.add_response('describe_volumes', response)
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.get_latest_volume_id_available("foobar")
        self.assertEqual(response, "newest")

    def test_no_volumes_found(self):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        response = {"Volumes": []}
        params = {'Filters': ANY}
        stubber.add_response('describe_volumes', response)
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.get_latest_volume_id_available("foobar")
        self.assertEqual(response, None)

    def test_raises_boto3_exception(self):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_client_error('describe_volumes', service_error_code="401")
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        with self.assertRaises(botocore.exceptions.ClientError):
            ebspin_ec2.get_latest_volume_id_available("foobar")


class get_latest_snapshot_id_test(unittest.TestCase):

    def test_can_get_latest_snapshot(self):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        response = {"Snapshots": [
            {"StartTime": datetime.datetime.now(), "State": "available", "SnapshotId": "old"},
            {"StartTime": datetime.datetime.now() + datetime.timedelta(days=1), "State": "available", "SnapshotId": "new"},
            {"StartTime": datetime.datetime.now() + datetime.timedelta(days=2), "State": "pending", "SnapshotId": "newest"}
        ]}
        params = {'Filters': ANY}
        stubber.add_response('describe_snapshots', response)
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.get_latest_snapshot_id("foobar")
        self.assertEqual(response, "newest")

    def test_no_snapshots_found(self):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        response = {"Snapshots": []}
        params = {'Filters': ANY}
        stubber.add_response('describe_snapshots', response)
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.get_latest_snapshot_id("foobar")
        self.assertEqual(response, None)

    def test_raises_boto3_exception(self):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_client_error('describe_snapshots', service_error_code="401")
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        with self.assertRaises(botocore.exceptions.ClientError):
            ebspin_ec2.get_latest_snapshot_id("foobar")


class attach_volume_test(unittest.TestCase):

    @patch('time.sleep')
    def test_can_wait_for_attach_volume(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_response(  # return no results as volume is "in-use"
            'describe_volumes',
            {"Volumes": []}
        )
        stubber.add_response(
            'describe_volumes',
            {
                "Volumes": [
                    {"CreateTime": datetime.datetime.now() + datetime.timedelta(days=2), "State": "available", "VolumeId": "foo"}
                ]
            }
        )
        stubber.add_response('attach_volume', {'AttachTime': datetime.datetime(2015, 1, 1)})
        stubber.add_response('describe_volumes', {"Volumes": []})  # return no results as volume is "available"
        stubber.add_response(
            'describe_volumes',
            {
                "Volumes": [
                    {
                        "State": "in-use",
                        "VolumeId": "foo",
                        "Attachments": [{"Device": "xvda", "InstanceId": "bar", "State": "attached"}]
                    }
                ]
            }
        )
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.attach_volume(volume_id="foo", instance_id="bar", device="xvda")
        self.assertEqual(response, "foo")


class create_snapshot_test(unittest.TestCase):

    @patch('time.sleep')
    def test_can_create_snapshot(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_response('create_snapshot', {"SnapshotId": "foo"})
        stubber.add_response('describe_volumes', {"Volumes": [{"Tags": [{"Key": "Name", "Value": "bar-/dev/xvda"}, {"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]}]})
        stubber.add_response('create_tags', {})
        stubber.add_response('describe_snapshots', {"Snapshots": []})
        stubber.add_response('describe_snapshots', {"Snapshots": [{"SnapshotId": "foo", "State": "completed"}]})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.create_snapshot("foo", {"extra": "tag"})
        self.assertEqual(response, "foo")


class create_volume_test(unittest.TestCase):

    @patch('time.sleep')
    def test_can_create_volume(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_response('create_volume', {"VolumeId": "foo"})
        stubber.add_response('describe_volumes', {"Volumes": [{"State": "in-use"}]})
        stubber.add_response('describe_volumes', {"Volumes": [{"State": "available"}]})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.create_volume(10, "gp2", "ap-southeast-2a")
        self.assertEqual(response, "foo")

    @patch('time.sleep')
    def test_can_create_volume_from_snapshot(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_response('create_volume', {"VolumeId": "foo"})
        stubber.add_response('describe_volumes', {"Volumes": [{"State": "in-use"}]})
        stubber.add_response('describe_volumes', {"Volumes": [{"State": "available"}]})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        response = ebspin_ec2.create_volume(10, "gp2", "ap-southeast-2a", "foo")
        self.assertEqual(response, "foo")

    @patch('time.sleep')
    def test_create_volume_with_exception(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_client_error('create_volume', service_error_code="401")
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        with self.assertRaises(botocore.exceptions.ClientError):
            ebspin_ec2.create_volume(10, "gp2", "ap-southeast-2a", "foo")

    @patch('time.sleep')
    def test_create_volume_with_waiter_exception(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.add_response('create_volume', {"VolumeId": "foo"})
        stubber.add_client_error('describe_volumes', service_error_code="401")
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        with self.assertRaises(botocore.exceptions.WaiterError):
            ebspin_ec2.create_volume(10, "gp2", "ap-southeast-2a", "foo")

class clean_old_volumes_test(unittest.TestCase):

    @patch('time.sleep')
    def test_can_clean_volumes(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        volumes = [
            {"VolumeId": "1", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "2", "State": "available", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "3", "State": "available", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]}
        ]
        stubber.add_response('describe_volumes', {"Volumes": volumes})
        stubber.add_response('delete_volume', [], {"VolumeId": "2"})
        stubber.add_response('delete_volume', [], {"VolumeId": "3"})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_old_volumes("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc", "1")

    @patch('time.sleep')
    def test_can_handle_multiple_volumes_in_use(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        volumes = [
            {"VolumeId": "1", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "2", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "3", "State": "available", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]}
        ]
        stubber.add_response('describe_volumes', {"Volumes": volumes})
        stubber.add_client_error('delete_volume', service_error_code='VolumeInUse', expected_params={"VolumeId": "2"})
        stubber.add_response('delete_volume', [], {"VolumeId": "3"})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_old_volumes("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc", "1")

    @patch('time.sleep')
    def test_no_old_volumes(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        volumes = [
            {"VolumeId": "1", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
        ]
        stubber.add_response('describe_volumes', {"Volumes": volumes})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_old_volumes("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc", "1")

class clean_old_volumes_test(unittest.TestCase):

    @patch('time.sleep')
    def test_can_clean_volumes(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        volumes = [
            {"VolumeId": "1", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "2", "State": "available", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "3", "State": "available", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]}
        ]
        stubber.add_response('describe_volumes', {"Volumes": volumes})
        stubber.add_response('delete_volume', [], {"VolumeId": "2"})
        stubber.add_response('delete_volume', [], {"VolumeId": "3"})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_old_volumes("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc", "1")

    @patch('time.sleep')
    def test_can_handle_multiple_volumes_in_use(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        volumes = [
            {"VolumeId": "1", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "2", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
            {"VolumeId": "3", "State": "available", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]}
        ]
        stubber.add_response('describe_volumes', {"Volumes": volumes})
        stubber.add_client_error('delete_volume', service_error_code='VolumeInUse', expected_params={"VolumeId": "2"})
        stubber.add_response('delete_volume', [], {"VolumeId": "3"})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_old_volumes("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc", "1")

    @patch('time.sleep')
    def test_no_old_volumes(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        volumes = [
            {"VolumeId": "1", "State": "in-use", "Tags": [{"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"}]},
        ]
        stubber.add_response('describe_volumes', {"Volumes": volumes})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_old_volumes("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc", "1")


class clean_snapshots_test(unittest.TestCase):

    @patch('time.sleep')
    def test_can_clean_snapshots(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        tags = [
            {"Key": "UUID", "Value": "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"},
            {"Key": "Name", "Value": "myvolume"},
        ]
        snapshots = [
            {"StartTime": datetime.datetime.now(), "State": "available", "SnapshotId": "old", "Tags": tags},
            {"StartTime": datetime.datetime.now() + datetime.timedelta(days=1), "State": "available", "SnapshotId": "new", "Tags": tags},
            {"StartTime": datetime.datetime.now() + datetime.timedelta(days=2), "State": "pending", "SnapshotId": "newest", "Tags": tags},
            {"StartTime": datetime.datetime.now() + datetime.timedelta(days=2), "State": "pending", "SnapshotId": "backup", "Tags": tags + [{"Key": "aws:dlm:lifecycle:schedule-name", "Value": "Default Schedule"}]},
        ]
        stubber.add_response('describe_snapshots', {"Snapshots": snapshots})
        stubber.add_response('delete_snapshot', [], {"SnapshotId": "old"})
        stubber.add_response('delete_snapshot', [], {"SnapshotId": "new"})
        stubber.add_response('delete_snapshot', [], {"SnapshotId": "newest"})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_snapshots("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc")
        stubber.assert_no_pending_responses()

    @patch('time.sleep')
    def test_no_snapshots(self, mock_sleep):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        snapshots = [
        ]
        stubber.add_response('describe_snapshots', {"Snapshots": snapshots})
        stubber.activate()
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_ec2.clean_snapshots("01c6b711-a7d4-4bdf-bb2b-10b4b60594bc")

class base_attach_test(unittest.TestCase):

    @patch('ebspin.ec2.Ec2.get_instance_name', return_value="bar")
    @patch('ebspin.ec2.Ec2.get_latest_volume_id_available', return_value=[])
    @patch('ebspin.ec2.Ec2.get_latest_snapshot_id', return_value=[])
    @patch('ebspin.ec2.Ec2.create_volume', return_value="foobar")
    @patch('ebspin.ec2.Ec2.tag_volume', return_value=[])
    @patch('ebspin.ec2.Ec2.attach_volume', return_value="barfoo")
    @patch('ebspin.ec2.Ec2.clean_old_volumes')
    @patch('ebspin.ec2.Ec2.clean_snapshots')
    def test_can_attach_new_volume(self, *args):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.activate()  # this is just to ensure that no real boto3 calls are made
        options = Mock()
        options.device = "/dev/xvdf"
        options.uuid = "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"
        options.size = 10
        options.type = "gp2"
        options.tags = {}
        ebspin_base = base.Base(options, metadata={"region": "ap-southeast-2", "availabilityZone": "ap-southeast-2a", "instanceId": "bar"})
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_base.ec2 = ebspin_ec2
        ebspin_base.attach()
        for arg in args:
            arg.assert_called()

    @patch('ebspin.ec2.Ec2.get_instance_name', return_value="bar")
    @patch('ebspin.ec2.Ec2.get_latest_volume_id_available', return_value="foo")
    @patch('ebspin.ec2.Ec2.get_volume_region', return_value="ap-southeast-2a")
    @patch('ebspin.ec2.Ec2.attach_volume', return_value="barfoo")
    @patch('ebspin.ec2.Ec2.clean_old_volumes')
    @patch('ebspin.ec2.Ec2.clean_snapshots')
    def test_can_attach_existing_volume_in_same_az(self, *args):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.activate()  # this is just to ensure that no real boto3 calls are made
        options = Mock()
        options.device = "/dev/xvdf"
        options.uuid = "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"
        options.size = 10
        options.type = "gp2"
        options.tags = {}
        ebspin_base = base.Base(options, metadata={"region": "ap-southeast-2", "availabilityZone": "ap-southeast-2a", "instanceId": "bar"})
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_base.ec2 = ebspin_ec2
        ebspin_base.attach()
        for arg in args:
            arg.assert_called()

    @patch('ebspin.ec2.Ec2.get_instance_name', return_value="bar")
    @patch('ebspin.ec2.Ec2.get_latest_volume_id_available', return_value="foo")
    @patch('ebspin.ec2.Ec2.get_volume_region', return_value="ap-southeast-2b")
    @patch('ebspin.ec2.Ec2.create_snapshot', return_value="my_snapshot")
    @patch('ebspin.ec2.Ec2.create_volume', return_value="my_volume")
    @patch('ebspin.ec2.Ec2.tag_volume', return_value=[])
    @patch('ebspin.ec2.Ec2.attach_volume', return_value="my_volume")
    @patch('ebspin.ec2.Ec2.clean_old_volumes')
    @patch('ebspin.ec2.Ec2.clean_snapshots')
    def test_can_attach_existing_volume_in_other_az(self, *args):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.activate()  # this is just to ensure that no real boto3 calls are made
        options = Mock()
        options.device = "/dev/xvdf"
        options.uuid = "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"
        options.size = 10
        options.type = "gp2"
        options.tags = {}
        ebspin_base = base.Base(options, metadata={"region": "ap-southeast-2", "availabilityZone": "ap-southeast-2a", "instanceId": "bar"})
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_base.ec2 = ebspin_ec2
        ebspin_base.attach()
        for arg in args:
            arg.assert_called()

    @patch('ebspin.ec2.Ec2.get_instance_name', return_value="bar")
    @patch('ebspin.ec2.Ec2.get_latest_volume_id_available', return_value=[])
    @patch('ebspin.ec2.Ec2.get_latest_snapshot_id', return_value="my_snapshot")
    @patch('ebspin.ec2.Ec2.create_volume', return_value="my_volume")
    @patch('ebspin.ec2.Ec2.tag_volume', return_value=[])
    @patch('ebspin.ec2.Ec2.attach_volume', return_value="my_volume")
    @patch('ebspin.ec2.Ec2.clean_old_volumes')
    @patch('ebspin.ec2.Ec2.clean_snapshots')
    def test_can_attach_volume_from_snapshot(self, *args):
        client = boto3.client('ec2')
        stubber = Stubber(client)
        stubber.activate()  # this is just to ensure that no real boto3 calls are made
        options = Mock()
        options.device = "/dev/xvdf"
        options.uuid = "01c6b711-a7d4-4bdf-bb2b-10b4b60594bc"
        options.size = 10
        options.type = "gp2"
        options.tags = {}
        ebspin_base = base.Base(options, metadata={"region": "ap-southeast-2", "availabilityZone": "ap-southeast-2a", "instanceId": "bar"})
        ebspin_ec2 = ec2.Ec2(client)
        ebspin_base.ec2 = ebspin_ec2
        ebspin_base.attach()
        for arg in args:
            arg.assert_called()

if __name__ == "__main__":
    unittest.main(verbosity=2)
