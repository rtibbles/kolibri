import copy
import json
import logging
import random
import uuid
from itertools import chain

from le_utils.constants import content_kinds
from le_utils.constants import format_presets
from le_utils.constants.labels.accessibility_categories import (
    ACCESSIBILITYCATEGORIESLIST,
)
from le_utils.constants.labels.learning_activities import LEARNINGACTIVITIESLIST
from le_utils.constants.labels.levels import LEVELSLIST
from le_utils.constants.labels.needs import NEEDSLIST
from le_utils.constants.labels.subjects import SUBJECTSLIST

from kolibri.core.content.models import ChannelMetadata
from kolibri.core.content.models import ContentNode
from kolibri.core.content.models import File
from kolibri.core.content.models import LocalFile
from kolibri.core.content.utils.content_types_tools import renderable_files_presets


logger = logging.getLogger(__name__)


def to_dict(instance):
    opts = instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(instance)
    return data


def uuid4_hex():
    return uuid.uuid4().hex


def choices(sequence, k):
    return [random.choice(sequence) for _ in range(0, k)]


class ChannelBuilder(object):
    """
    This class is purely to generate all the relevant data for a single
    channel for use during testing.

    Can work with different model classes via dependency injection to support
    both current models and historic schema versions.
    """

    __TREE_CACHE = {}

    tree_keys = (
        "channel",
        "files",
        "localfiles",
        "node_to_files_map",
        "localfile_to_files_map",
        "root_node",
    )

    # Realistic content libraries organized by subject and content kind
    MATH_CONTENT = {
        content_kinds.VIDEO: [
            ("Introduction to Algebra", "Learn fundamental algebraic concepts including variables, expressions, and basic equation solving"),
            ("Quadratic Equations Explained", "Master the techniques for solving quadratic equations using factoring, completing the square, and the quadratic formula"),
            ("Geometry Basics", "Explore the fundamental concepts of shapes, angles, and spatial relationships"),
            ("Fractions and Decimals", "Understanding numerical representations and conversions between fractions and decimals"),
        ],
        content_kinds.EXERCISE: [
            ("Practice: Linear Equations", "Solve problems involving single-variable linear equations with step-by-step guidance"),
            ("Quiz: Basic Arithmetic", "Test your knowledge of addition, subtraction, multiplication, and division"),
            ("Challenge: Word Problems", "Apply mathematical concepts to solve real-world scenarios"),
        ],
        content_kinds.DOCUMENT: [
            ("Algebra Study Guide", "Comprehensive reference material covering algebraic principles and problem-solving strategies"),
            ("Mathematics Formula Sheet", "Quick reference guide for essential mathematical formulas and theorems"),
        ],
        content_kinds.AUDIO: [
            ("Mathematics Podcast: Problem Solving", "Audio discussion of mathematical problem-solving techniques and strategies"),
            ("Learn Math Through Stories", "Engaging audio content that teaches mathematical concepts through narratives"),
        ],
    }

    SCIENCE_CONTENT = {
        content_kinds.VIDEO: [
            ("The Water Cycle", "Understanding how water moves through Earth's systems via evaporation, condensation, and precipitation"),
            ("Photosynthesis Explained", "Learn how plants convert sunlight into energy through the process of photosynthesis"),
            ("Newton's Laws of Motion", "Explore the three fundamental laws that describe the relationship between objects and forces"),
            ("Cell Structure and Function", "Discover the basic building blocks of life and how cells operate"),
        ],
        content_kinds.EXERCISE: [
            ("Practice: Scientific Method", "Apply the scientific method to solve problems and design experiments"),
            ("Quiz: States of Matter", "Test your understanding of solids, liquids, gases, and phase transitions"),
        ],
        content_kinds.DOCUMENT: [
            ("Biology Lab Guide", "Step-by-step instructions for conducting biology experiments safely and effectively"),
            ("Chemistry Reference Tables", "Periodic table and essential chemistry data for students"),
        ],
        content_kinds.AUDIO: [
            ("Science Podcast: Climate Change", "Audio exploration of climate science and environmental changes"),
        ],
    }

    MIXED_CONTENT = {
        content_kinds.TOPIC: [
            ("Learning Resources", "Root topic containing various educational materials"),
            ("Advanced Topics", "Collection of advanced learning resources across multiple subjects"),
            ("Foundational Concepts", "Essential knowledge for building a strong academic foundation"),
        ],
    }

    def __init__(self, levels=3, num_children=5, realistic=True, subject='mixed', models=None):
        self.levels = levels
        self.num_children = num_children
        self.realistic = realistic
        self.subject = subject

        self.modified = set()

        # Dependency injection for models
        if models is None:
            self.models = {
                'ChannelMetadata': ChannelMetadata,
                'ContentNode': ContentNode,
                'File': File,
                'LocalFile': LocalFile,
            }
        else:
            self.models = models

        try:
            self.load_data()
        except KeyError:
            self.generate_new_tree()
            self.save_data()

        self.generate_nodes_from_root_node()

    @property
    def cache_key(self):
        return "{}_{}".format(self.levels, self.num_children)

    def _get_content_library_for_subject(self):
        """Get the appropriate content library based on subject"""
        if self.subject == 'math':
            return self.MATH_CONTENT
        elif self.subject == 'science':
            return self.SCIENCE_CONTENT
        else:
            # For mixed, combine both
            combined = {}
            for kind in set(list(self.MATH_CONTENT.keys()) + list(self.SCIENCE_CONTENT.keys())):
                combined[kind] = (
                    self.MATH_CONTENT.get(kind, []) +
                    self.SCIENCE_CONTENT.get(kind, [])
                )
            return combined

    def _get_realistic_title_description(self, kind):
        """Get realistic title and description for a content kind"""
        if not self.realistic:
            return "Test", "Blah blah blah"

        content_library = self._get_content_library_for_subject()

        if kind in content_library and content_library[kind]:
            title, description = random.choice(content_library[kind])
            return title, description
        elif kind == content_kinds.TOPIC and self.MIXED_CONTENT.get(content_kinds.TOPIC):
            title, description = random.choice(self.MIXED_CONTENT[content_kinds.TOPIC])
            return title, description
        else:
            # Fallback to generic realistic content
            return self._generate_generic_realistic_content(kind)

    def _generate_generic_realistic_content(self, kind):
        """Generate generic but realistic content for any kind"""
        kind_titles = {
            content_kinds.VIDEO: "Educational Video",
            content_kinds.EXERCISE: "Practice Exercise",
            content_kinds.DOCUMENT: "Study Material",
            content_kinds.AUDIO: "Audio Lesson",
            content_kinds.TOPIC: "Learning Topic",
            content_kinds.HTML5: "Interactive Content",
        }
        kind_descriptions = {
            content_kinds.VIDEO: "Informative video content for learning",
            content_kinds.EXERCISE: "Practice problems to reinforce learning",
            content_kinds.DOCUMENT: "Reading material and reference content",
            content_kinds.AUDIO: "Audio-based educational content",
            content_kinds.TOPIC: "Collection of related learning resources",
            content_kinds.HTML5: "Interactive learning application",
        }
        title = kind_titles.get(kind, "Educational Content")
        description = kind_descriptions.get(kind, "Learning resource for students")
        return title, description

    def _get_realistic_author(self):
        """Get a realistic author name"""
        if not self.realistic:
            return ""
        authors = [
            "Kolibri Content Team",
            "Educational Content Creators",
            "Learning Equity",
            "Open Education Resources",
        ]
        return random.choice(authors)

    def _get_appropriate_license(self):
        """Get an appropriate license name"""
        licenses = ["CC BY", "CC BY-SA", "CC BY-NC", "CC BY-NC-SA"]
        return random.choice(licenses)

    def generate_new_tree(self):
        self.channel = self.channel_data()
        self.files = {}
        self.localfiles = {}
        self.node_to_files_map = {}
        self.localfile_to_files_map = {}

        self.root_node = self.generate_topic()
        self.channel["root_id"] = self.root_node["id"]

        if self.levels:
            self.root_node["children"] = self.recurse_and_generate(
                self.root_node["id"], self.levels
            )

    def load_data(self):
        try:
            data = copy.deepcopy(self.__TREE_CACHE[self.cache_key])

            for key in self.tree_keys:
                setattr(self, key, data[key])
        except KeyError:
            logger.info(
                "No tree cache found for {} levels and {} children per level".format(
                    self.levels, self.num_children
                )
            )
            raise

    def save_data(self):
        data = {}

        for key in self.tree_keys:
            data[key] = getattr(self, key)

        self.__TREE_CACHE[self.cache_key] = copy.deepcopy(data)

    def generate_nodes_from_root_node(self):
        self._django_nodes = self.models['ContentNode'].objects.build_tree_nodes(self.root_node)

        self.nodes = {n["id"]: n for n in map(to_dict, self._django_nodes)}

    def insert_into_default_db(self):
        self.models['ContentNode'].objects.bulk_create(self._django_nodes)
        self.models['ChannelMetadata'].objects.create(**self.channel)
        self.models['LocalFile'].objects.bulk_create(
            (self.models['LocalFile'](**l) for l in self.localfiles.values())
        )
        self.models['File'].objects.bulk_create(
            (self.models['File'](**f) for f in self.files.values())
        )

    def recurse_tree_until_leaf_container(self, parent):
        if not parent.get("children"):
            parent["children"] = []
            return parent
        child = random.choice(parent["children"])
        if child["kind"] != content_kinds.TOPIC:
            return parent
        return self.recurse_tree_until_leaf_container(child)

    def delete_file(self, file):
        try:
            index = self.localfile_to_files_map[file["local_file_id"]].index(file["id"])
            self.localfile_to_files_map[file["local_file_id"]].pop(index)
        except ValueError:
            pass
        if not self.localfile_to_files_map[file["local_file_id"]]:
            del self.localfiles[file["local_file_id"]]
        del self.files[file["id"]]

    def update_resource(self, resource):
        """
        Update any main files for the resource
        """
        new_localfiles = []
        keys_to_remove = set()
        # Make a copy of the node to file map
        # as it will otherwise change during iteration
        node_to_files_map = list(self.node_to_files_map[resource["id"]])
        for f_id in node_to_files_map:
            file = self.files[f_id]
            if not file["supplementary"]:
                self.delete_file(file)
                # Create a new file in its place
                localfile = self.localfile_data()
                self.file_data(
                    resource["id"], localfile["id"], preset=format_presets.VIDEO_LOW_RES
                )
                keys_to_remove.add(f_id)
                new_localfiles.append(localfile)
        self.node_to_files_map[resource["id"]] = list(
            filter(
                lambda x: x not in keys_to_remove,
                self.node_to_files_map[resource["id"]],
            )
        )
        return new_localfiles

    def update_thumbnail(self, node):
        """
        Update the thumbnail for a node
        """
        new_localfiles = []
        keys_to_remove = set()
        # Make a copy of the node to file map
        # as it will otherwise change during iteration
        node_to_files_map = list(self.node_to_files_map[node["id"]])
        for f_id in node_to_files_map:
            file = self.files[f_id]
            if file["thumbnail"]:
                self.delete_file(file)
                # Create a new file in its place
                thumbnail = self.localfile_data(extension="png")
                self.file_data(
                    node["id"],
                    thumbnail["id"],
                    thumbnail=True,
                    preset=format_presets.TOPIC_THUMBNAIL,
                )
                keys_to_remove.add(f_id)
                new_localfiles.append(thumbnail)
        self.node_to_files_map[node["id"]] = list(
            filter(
                lambda x: x not in keys_to_remove, self.node_to_files_map[node["id"]]
            )
        )
        return new_localfiles

    def delete_resource_files(self, resource):
        for f_id in self.node_to_files_map[resource["id"]]:
            file = self.files[f_id]
            self.delete_file(file)
        del self.node_to_files_map[resource["id"]]

    def duplicate_resource(self, resource):
        node = self.contentnode_data(
            parent_id=resource["parent_id"],
            content_id=resource["content_id"],
            kind=resource["kind"],
        )
        for f_id in self.node_to_files_map[resource["id"]]:
            file = self.files[f_id]
            self.file_data(
                node["id"],
                file["local_file_id"],
                thumbnail=file["thumbnail"],
                preset=file["preset"],
            )
        return node

    def duplicate_resources(self, num_resources):
        self.duplicated_resources = []
        for i in range(0, num_resources):
            child = None
            while child is None or child["id"] in self.modified:
                parent = self.recurse_tree_until_leaf_container(self.root_node)
                child = random.choice(parent["children"])
            duplicate = self.duplicate_resource(child)
            self.duplicated_resources.append(duplicate)
            parent["children"].append(duplicate)
            self.modified.add(duplicate["id"])
        self.generate_nodes_from_root_node()

    def move_resources(self, num_resources):
        self.moved_resources = []
        self.deleted_resources = []
        for i in range(0, num_resources):
            child = None
            while child is None or child["id"] in self.modified:
                parent = self.recurse_tree_until_leaf_container(self.root_node)
                child = random.choice(parent["children"])
            moved = self.duplicate_resource(child)
            self.moved_resources.append(moved)
            self.deleted_resources.append(child)
            parent["children"].pop(parent["children"].index(child))
            parent["children"].append(moved)
            self.modified.add(moved["id"])
        self.generate_nodes_from_root_node()

    def upgrade(self, new_resources=0, updated_resources=0, deleted_resources=0):
        self.new_resources = []
        self.updated_thumbnails = []
        for i in range(0, new_resources):
            parent = self.recurse_tree_until_leaf_container(self.root_node)
            child = self.generate_leaf(parent["id"])
            parent["children"].append(child)
            self.new_resources.append(child)
            # To emulate a common occurrence that produces edge cases
            # we also update the parent's thumbnail here
            self.updated_thumbnails.extend(self.update_thumbnail(parent))
            self.modified.add(child["id"])

        self.updated_resources = []
        self.updated_resource_localfiles = []
        for i in range(0, updated_resources):
            child = None
            while child is None or child["id"] in self.modified:
                parent = self.recurse_tree_until_leaf_container(self.root_node)
                child = random.choice(parent["children"])
            self.updated_resource_localfiles.extend(self.update_resource(child))
            self.updated_resources.append(child)
            self.modified.add(child["id"])

        self.deleted_resources = []
        for i in range(0, deleted_resources):
            child = None
            while child is None or child["id"] in self.modified:
                parent = self.recurse_tree_until_leaf_container(self.root_node)
                child_index = random.randint(0, len(parent["children"]) - 1)
                child = parent["children"][child_index]
            child = parent["children"].pop(child_index)
            self.delete_resource_files(child)
            self.deleted_resources.append(child)

        self.generate_nodes_from_root_node()

    @property
    def resources(self):
        return filter(lambda x: x["kind"] != content_kinds.TOPIC, self.nodes.values())

    def get_resource_localfiles(self, ids):
        localfiles = {}
        for r in ids:
            for f in self.node_to_files_map.get(r, []):
                file = self.files[f]
                localfile = self.localfiles[file["local_file_id"]]
                localfiles[localfile["id"]] = localfile
        return list(localfiles.values())

    @property
    def data(self):
        contentnode_list = []
        for node in self.nodes.values():
            node["ancestors"] = json.dumps(node["ancestors"])
            contentnode_list.append(node)

        return {
            "content_channel": [self.channel],
            "content_contentnode": contentnode_list,
            "content_file": list(self.files.values()),
            "content_localfile": list(self.localfiles.values()),
        }

    def recurse_and_generate(self, parent_id, levels):
        children = []
        for i in range(0, self.num_children):
            if levels == 0:
                node = self.generate_leaf(parent_id)
            else:
                node = self.generate_topic(parent_id=parent_id)
                node["children"] = self.recurse_and_generate(node["id"], levels - 1)
            children.append(node)
        return children

    def generate_topic(self, parent_id=None):
        data = self.contentnode_data(
            kind=content_kinds.TOPIC, root=parent_id is None, parent_id=parent_id
        )
        thumbnail = self.localfile_data(extension="png")
        self.file_data(
            data["id"],
            thumbnail["id"],
            thumbnail=True,
            preset=format_presets.TOPIC_THUMBNAIL,
        )
        return data

    def generate_leaf(self, parent_id):
        node = self.contentnode_data(parent_id=parent_id, kind=content_kinds.VIDEO)
        localfile = self.localfile_data()
        thumbnail = self.localfile_data(extension="png")
        self.file_data(node["id"], localfile["id"], preset=format_presets.VIDEO_LOW_RES)
        self.file_data(
            node["id"],
            thumbnail["id"],
            thumbnail=True,
            preset=format_presets.VIDEO_THUMBNAIL,
        )
        return node

    def channel_data(self, channel_id=None, version=1):
        if self.realistic:
            name = "Educational Content Library"
            description = "Comprehensive educational resources for testing content import and export"
            author = "Kolibri Content Team"
        else:
            name = "testing"
            description = "Test channel"
            author = "Outis"

        return {
            "root_id": None,
            "last_updated": None,
            "version": version,
            "author": author,
            "description": description,
            "tagline": None,
            "min_schema_version": "1",
            "thumbnail": "",
            "name": name,
            "id": channel_id or uuid4_hex(),
        }

    def localfile_data(self, extension="mp4"):
        data = {
            "file_size": random.randint(1, 1000),
            "extension": extension,
            "available": False,
            "id": uuid4_hex(),
        }

        self.localfiles[data["id"]] = data

        return data

    def file_data(
        self,
        contentnode_id,
        local_file_id,
        thumbnail=False,
        preset=None,
        supplementary=False,
    ):
        data = {
            "priority": None,
            "supplementary": supplementary or thumbnail,
            "id": uuid4_hex(),
            "local_file_id": local_file_id or uuid4_hex(),
            "contentnode_id": contentnode_id,
            "thumbnail": thumbnail,
            "preset": preset or random.choice(list(renderable_files_presets)),
            "lang_id": None,
        }
        self.files[data["id"]] = data
        if contentnode_id not in self.node_to_files_map:
            self.node_to_files_map[contentnode_id] = []
        self.node_to_files_map[contentnode_id].append(data["id"])
        if local_file_id not in self.localfile_to_files_map:
            self.localfile_to_files_map[local_file_id] = []
        self.localfile_to_files_map[local_file_id].append(data["id"])
        return data

    def contentnode_data(
        self, node_id=None, content_id=None, parent_id=None, kind=None, root=False
    ):
        # First kind in choices is Topic, so exclude it here.
        kind = kind or random.choice(content_kinds.choices[1:])[0]

        # Get realistic content
        title, description = self._get_realistic_title_description(kind)
        author = self._get_realistic_author()
        license_name = self._get_appropriate_license()

        return {
            "options": "{}",
            "content_id": content_id or uuid4_hex(),
            "channel_id": self.channel["id"],
            "description": description,
            "id": node_id or uuid4_hex(),
            "license_name": license_name,
            "license_owner": "",
            "license_description": None,
            "lang_id": None,
            "author": author,
            "title": title,
            "parent_id": None if root else parent_id or uuid4_hex(),
            "kind": kind,
            "coach_content": False,
            "available": False,
            "learning_activities": ",".join(
                set(choices(LEARNINGACTIVITIESLIST, k=random.randint(1, 3)))
            ),
            "accessibility_labels": ",".join(
                set(choices(ACCESSIBILITYCATEGORIESLIST, k=random.randint(1, 3)))
            ),
            "grade_levels": ",".join(set(choices(LEVELSLIST, k=random.randint(1, 2)))),
            "categories": ",".join(set(choices(SUBJECTSLIST, k=random.randint(1, 10)))),
            "learner_needs": ",".join(set(choices(NEEDSLIST, k=random.randint(1, 5)))),
        }
