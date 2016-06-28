"""
To run this test, type this in command line <kolibri manage test -- kolibri.content>
"""
import os
import shutil
import tempfile
from django.test import TestCase
from django.core.urlresolvers import reverse
from django.db import connections, IntegrityError
from django.test.utils import override_settings
from kolibri.content import models as content
from kolibri.content import api
from django.conf import settings
from django.core.exceptions import ValidationError

from ..constants import content_kinds
from ..content_db_router import set_active_content_database

from rest_framework.test import APITestCase


@override_settings(
    CONTENT_COPY_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+"/test_content_copy"
)
class ContentNodeTestCase(TestCase):
    """
    Testcase for content metadata methods
    """
    fixtures = ['channel_test.json', 'content_test.json']
    multi_db = True
    the_channel_id = 'content_test'
    connections.databases[the_channel_id] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }

    def setUp(self):

        # set the active content database for the duration of the test
        set_active_content_database(self.the_channel_id)

        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        # Create files in the temporary directory
        self.temp_f_1 = open(os.path.join(self.test_dir, 'test_1.pdf'), 'wb')
        self.temp_f_2 = open(os.path.join(self.test_dir, 'test_2.mp4'), 'wb')
        # Write something to it
        self.temp_f_1.write(('The owls are not what they seem').encode('utf-8'))
        self.temp_f_2.write(('The owl are not what they seem').encode('utf-8'))

        # Reopen the file and check if what we read back is the same
        self.temp_f_1 = open(os.path.join(self.test_dir, 'test_1.pdf'))
        self.temp_f_2 = open(os.path.join(self.test_dir, 'test_2.mp4'))
        self.assertEqual(self.temp_f_1.read(), 'The owls are not what they seem')
        self.assertEqual(self.temp_f_2.read(), 'The owl are not what they seem')

    """Tests for content API methods"""
    def test_can_get_content_with_id(self):

        # pass content_id
        root_id = content.ContentNode.objects.get(title="root").content_id
        expected_output = content.ContentNode.objects.filter(title__in=["c1", "c2"])
        actual_output = api.immediate_children(channel_id=self.the_channel_id, content=str(root_id))
        self.assertEqual(set(expected_output), set(actual_output))

        # pass content_ids
        api.set_is_related(channel_id=self.the_channel_id, content1=str(expected_output[0].content_id), content2=str(root_id))

        # pass invalid type
        with self.assertRaises(TypeError):
            api.immediate_children(channel_id=self.the_channel_id, content=432)

    def test_get_content_with_id(self):

        # test for single content_id
        the_content_id = content.ContentNode.objects.get(title="root").content_id
        expected_output = content.ContentNode.objects.filter(title="root")
        actual_output = api.get_content_with_id(self.the_channel_id, the_content_id)
        self.assertEqual(set(expected_output), set(actual_output))

        # test for a list of content_ids
        the_content_ids = [cm.content_id for cm in content.ContentNode.objects.all() if cm.title in ["root", "c1", "c2c2"]]
        expected_output2 = content.ContentNode.objects.filter(title__in=["root", "c1", "c2c2"])
        actual_output2 = api.get_content_with_id(self.the_channel_id, the_content_ids)
        self.assertEqual(set(expected_output2), set(actual_output2))

        # test ContentNode __str__ method
        self.assertEqual(actual_output[0].__str__(), 'root')

        # test License __str__ method
        self.assertEqual(actual_output[0].license.__str__(), 'WTFPL')

    def test_get_ancestor_topics(self):

        p = content.ContentNode.objects.get(title="c2c3")
        expected_output = content.ContentNode.objects.filter(title__in=["root", "c2"])
        actual_output = api.get_ancestor_topics(channel_id=self.the_channel_id, content=p)
        self.assertEqual(set(expected_output), set(actual_output))

    def test_immediate_children(self):

        p = content.ContentNode.objects.get(title="root")
        expected_output = content.ContentNode.objects.filter(title__in=["c1", "c2"])
        actual_output = api.immediate_children(channel_id=self.the_channel_id, content=p)
        self.assertEqual(set(expected_output), set(actual_output))

    def test_leaves(self):

        p = content.ContentNode.objects.get(title="c2")
        expected_output = content.ContentNode.objects.filter(title__in=["c2c1", "c2c2", "c2c3"])
        actual_output = api.leaves(channel_id=self.the_channel_id, content=p)
        self.assertEqual(set(expected_output), set(actual_output))

    def test_get_missing_files(self):

        # for non-topic contentnode
        p = content.ContentNode.objects.get(title="c1")
        expected_output = content.File.objects.filter(id__in=[1, 2])
        actual_output = api.get_missing_files(channel_id=self.the_channel_id, content=p)
        self.assertEqual(set(expected_output), set(actual_output))
        # for topic contentnode
        p = content.ContentNode.objects.get(title="c2")
        expected_output = content.File.objects.filter(id__in=[3, 4, 5])
        actual_output = api.get_missing_files(channel_id=self.the_channel_id, content=p)
        self.assertEqual(set(expected_output), set(actual_output))

    def test_get_all_prerequisites(self):
        """
        test the directional characteristic of prerequisite relationship
        """

        c1 = content.ContentNode.objects.get(title="c1")
        root = content.ContentNode.objects.get(title="root")
        # if root is the prerequisite of c1
        expected_output = content.ContentNode.objects.filter(title__in=["root"])
        actual_output = api.get_all_prerequisites(channel_id=self.the_channel_id, content=c1)
        self.assertEqual(set(expected_output), set(actual_output))
        # then c1 should not be the prerequisite of root
        expected_output = content.ContentNode.objects.filter(title__in=["c1"])
        actual_output = api.get_all_prerequisites(channel_id=self.the_channel_id, content=root)
        self.assertNotEqual(set(actual_output), set(expected_output))

    def test_get_all_related(self):
        """
        test the nondirectional characteristic of related relationship
        """

        c1 = content.ContentNode.objects.get(title="c1")
        c2 = content.ContentNode.objects.get(title="c2")
        # if c1 is related to c2
        expected_output = content.ContentNode.objects.filter(title__in=["c2"])
        actual_output = api.get_all_related(channel_id=self.the_channel_id, content=c1)
        self.assertEqual(set(expected_output), set(actual_output))
        # then c2 should be related to c1
        expected_output = content.ContentNode.objects.filter(title__in=["c1"])
        actual_output = api.get_all_related(channel_id=self.the_channel_id, content=c2)
        self.assertEqual(set(expected_output), set(actual_output))

    def test_set_prerequisite(self):

        root = content.ContentNode.objects.get(title="root")
        c2 = content.ContentNode.objects.get(title="c2")
        self.assertFalse(api.get_all_prerequisites(channel_id=self.the_channel_id, content=root))
        api.set_prerequisite(channel_id=self.the_channel_id, target_node=root, prerequisite=c2)
        self.assertTrue(api.get_all_prerequisites(channel_id=self.the_channel_id, content=root))

    def test_set_prerequisite_self_reference(self):

        c2 = content.ContentNode.objects.get(title="c2")
        # test for self reference exception
        with self.assertRaises(IntegrityError):
            api.set_prerequisite(channel_id=self.the_channel_id, target_node=c2, prerequisite=c2)

    def test_set_prerequisite_uniqueness(self):

        root = content.ContentNode.objects.get(title="root")
        c2 = content.ContentNode.objects.get(title="c2")
        api.set_prerequisite(channel_id=self.the_channel_id, target_node=c2, prerequisite=root)
        # test for uniqueness exception
        with self.assertRaises(ValidationError):
            api.set_prerequisite(channel_id=self.the_channel_id, target_node=c2, prerequisite=root)

    def test_set_prerequisite_immediate_cyclic(self):

        root = content.ContentNode.objects.get(title="root")
        c2 = content.ContentNode.objects.get(title="c2")
        api.set_prerequisite(channel_id=self.the_channel_id, target_node=c2, prerequisite=root)
        # test for immediate cyclic exception
        with self.assertRaises(IntegrityError):
            api.set_prerequisite(channel_id=self.the_channel_id, target_node=root, prerequisite=c2)

    # <the exception hasn't been implemented yet, may add in the future>
    # def test_set_prerequisite_distant_cyclic(self):
    #     root = content.ContentNode.objects.get(title="root")
    #     c2 = content.ContentNode.objects.get(title="c2")
    #     api.set_prerequisite(channel_id=self.the_channel_id, target_node=root, prerequisite=c2)
    #     # test for distant cyclic exception
    #     c1 = content.ContentNode.objects.get(title="c1")
    #     with self.assertRaises(Exception):
    #         api.set_prerequisite(channel_id=self.the_channel_id, target_node=c2, prerequisite=c1)

    def test_set_is_related(self):

        root = content.ContentNode.objects.get(title="root")
        c1 = content.ContentNode.objects.get(title="c1")
        self.assertFalse(root in api.get_all_related(channel_id=self.the_channel_id, content=c1))
        api.set_is_related(channel_id=self.the_channel_id, content1=c1, content2=root)
        self.assertTrue(root in api.get_all_related(channel_id=self.the_channel_id, content=c1))

    def test_set_is_related_self_reference(self):

        c1 = content.ContentNode.objects.get(title="c1")
        # test for self reference exception
        with self.assertRaises(IntegrityError):
            api.set_is_related(channel_id=self.the_channel_id, content1=c1, content2=c1)

    def test_set_is_related_uniqueness(self):

        root = content.ContentNode.objects.get(title="root")
        c1 = content.ContentNode.objects.get(title="c1")
        api.set_is_related(channel_id=self.the_channel_id, content1=c1, content2=root)
        # test for uniqueness exception
        with self.assertRaises(IntegrityError):
            api.set_is_related(channel_id=self.the_channel_id, content1=c1, content2=root)

    def test_set_is_related_immediate_cyclic(self):

        root = content.ContentNode.objects.get(title="root")
        c1 = content.ContentNode.objects.get(title="c1")
        api.set_is_related(channel_id=self.the_channel_id, content1=c1, content2=root)
        # test for silently canceling save on immediate cyclic related_relationship
        try:
            api.set_is_related(channel_id=self.the_channel_id, content1=root, content2=c1)
        except:
            self.assertTrue(False)

    def test_children_of_kind(self):

        p = content.ContentNode.objects.get(title="root")
        expected_output = content.ContentNode.objects.filter(title__in=["c2", "c2c2", "c2c3"])
        actual_output = api.children_of_kind(channel_id=self.the_channel_id, content=p, kind=content_kinds.TOPIC)
        self.assertEqual(set(expected_output), set(actual_output))

    def test_all_str(self):

        # test for File __str__
        p = content.File.objects.get(id=2)
        self.assertEqual(str(p), '.mp4')
        # test for ContentTag __str__
        p = content.ContentTag.objects.get(tag_name="tag_2")
        self.assertEqual(str(p), 'tag_2')
        # test for Language __str__
        p = content.Language.objects.get(lang_code="en")
        self.assertEqual(str(p), 'en')
        # test for ChannelMetadata __str__
        p = content.ChannelMetadata.objects.get(name="testing")
        self.assertEqual(str(p), 'testing')

    def tearDown(self):
        """
        clean up files/folders created during the test
        """
        # set the active content database to None now that the test is over
        set_active_content_database(None)
        try:
            shutil.rmtree(settings.CONTENT_COPY_DIR)
            shutil.rmtree(self.test_dir)
        except:
            pass
        super(ContentNodeTestCase, self).tearDown()


class ContentNodeAPITestCase(APITestCase):
    """
    Testcase for content API methods
    """
    fixtures = ['channel_test.json', 'content_test.json']
    multi_db = True
    the_channel_id = 'content_test'
    connections.databases[the_channel_id] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }

    def setUp(self):
        # set the active content database for the duration of the test
        set_active_content_database(self.the_channel_id)

    def _reverse_channel_url(self, pattern_name, extra_kwargs):
        """Helper method to reverse a URL using the current channel ID"""
        kwargs = {"channelmetadata_channel_id": self.the_channel_id}
        kwargs.update(extra_kwargs)
        return reverse(pattern_name, kwargs=kwargs)

    def test_ancestor_topics_endpoint(self):
        c1_id = content.ContentNode.objects.get(title="c1").content_id
        response = self.client.get(self._reverse_channel_url("contentnode-ancestor-topics", {"content_id": c1_id}))
        self.assertEqual(response.data[0]['title'], 'root')

    def test_immediate_children_endpoint(self):
        root_id = content.ContentNode.objects.get(title="root").content_id
        response = self.client.get(self._reverse_channel_url("contentnode-immediate-children", {"content_id": root_id}))
        self.assertEqual(response.data[0]['title'], 'c1')
        self.assertEqual(response.data[1]['title'], 'c2')

    def test_leaves_endpoint(self):
        root_id = content.ContentNode.objects.get(title="root").content_id
        response = self.client.get(self._reverse_channel_url("contentnode-leaves", {"content_id": root_id}))
        self.assertEqual(response.data[0]['title'], 'c1')
        self.assertEqual(response.data[1]['title'], 'c2c1')
        self.assertEqual(response.data[2]['title'], 'c2c2')
        self.assertEqual(response.data[3]['title'], 'c2c3')

    def test_all_prerequisites_endpoint(self):
        c1_id = content.ContentNode.objects.get(title="c1").content_id
        response = self.client.get(self._reverse_channel_url("contentnode-all-prerequisites", {"content_id": c1_id}))
        self.assertEqual(response.data[0]['title'], 'root')

    def test_all_related_endpoint(self):
        c1_id = content.ContentNode.objects.get(title="c1").content_id
        response = self.client.get(self._reverse_channel_url("contentnode-all-related", {"content_id": c1_id}))
        self.assertEqual(response.data[0]['title'], 'c2')

    def test_missing_files_endpoint(self):
        c1_id = content.ContentNode.objects.get(title="c1").content_id
        response = self.client.get(self._reverse_channel_url("contentnode-missing-files", {"content_id": c1_id}))
        expected_output = content.File.objects.filter(id__in=[1, 2])
        self.assertEqual(response.data[0]['id'], expected_output[0].id)
        self.assertEqual(response.data[1]['id'], expected_output[1].id)

    def test_contentnode_list(self):
        response = self.client.get(self._reverse_channel_url("contentnode-list", {}))
        self.assertEqual(len(response.data), 6)

    def test_contentnode_retrieve(self):
        c1_id = str(content.ContentNode.objects.get(title="c1").content_id)
        response = self.client.get(self._reverse_channel_url("contentnode-detail", {'content_id': c1_id}))
        self.assertEqual(response.data['content_id'], c1_id)

    def test_channelmetadata_list(self):
        response = self.client.get(reverse("channelmetadata-list", kwargs={}))
        self.assertEqual(response.data[0]['name'], 'testing')

    def test_channelmetadata_retrieve(self):
        channel_id = str(content.ChannelMetadata.objects.get(name="testing").channel_id)
        response = self.client.get(reverse("channelmetadata-detail", kwargs={'channel_id': channel_id}))
        self.assertEqual(response.data['name'], 'testing')

    def test_file_list(self):
        response = self.client.get(self._reverse_channel_url("file-list", {}))
        self.assertEqual(len(response.data), 5)

    def test_file_retrieve(self):
        response = self.client.get(self._reverse_channel_url("file-detail", {'pk': 1}))
        self.assertEqual(response.data['preset'], 'high_res_video')

    def tearDown(self):
        """
        clean up files/folders created during the test
        """
        # set the active content database to None now that the test is over
        set_active_content_database(None)
        super(ContentNodeAPITestCase, self).tearDown()
