"""
Preset configurations for generating test fixtures using ChannelBuilder.

Each function creates and returns a ChannelBuilder configured for a specific
test scenario. These presets define the canonical content trees that are used
across all schema versions.
"""

from le_utils.constants import content_kinds
from le_utils.constants import format_presets

from kolibri.core.content.test.helpers import ChannelBuilder


def create_basic_content_fixture(models=None):
    """
    Creates the standard content fixture used across test files.

    This generates a realistic version of the content tree that was previously
    defined in content_test.json and content_import_test.json, with:
    - Meaningful titles instead of "c1", "c2", "c1c2"
    - Realistic descriptions instead of "balbla1", "balbla2"
    - Appropriate licenses and authors

    Tree structure:
      Root: "Learning Resources"
        ├─ Video: "Introduction to Algebra"
        │   (has prerequisite: root, related to: Advanced Mathematics)
        ├─ Topic: "Advanced Mathematics"
        │   ├─ Exercise: "Linear Equations Practice"
        │   ├─ Document: "Algebra Study Guide"
        │   └─ Audio: "Mathematics Podcast"
        └─ Audio: "Sample Audio Resource" (no license)

    Args:
        models: Optional dict of model classes to use for dependency injection.
                If None, uses default kolibri.core.content.models.

    Returns:
        ChannelBuilder instance ready to insert_into_default_db()
    """
    # Create builder with realistic=False initially so we can manually set content
    builder = ChannelBuilder(
        levels=0,
        num_children=0,
        realistic=False,  # We'll set titles manually for precise control
        models=models
    )

    # Use specific channel ID for compatibility with existing tests
    builder.channel = builder.channel_data(
        channel_id="6199dde695db4ee4ab392222d5af1e5c",
        version=0
    )
    builder.channel.update({
        "name": "Educational Content Library",
        "description": "Comprehensive educational resources for testing content import and export",
        "author": "Kolibri Content Team",
    })

    # Build the tree structure manually for precise control
    # Root node (was "root")
    root = builder.generate_topic(parent_id=None)
    root["id"] = "da7ecc42e62553eebc8121242746e88a"
    root["content_id"] = "ffdfadc415214ec0b1438f002f23d7bf"
    root["title"] = "Learning Resources"
    root["description"] = "Root topic containing various educational materials"
    root["license_name"] = "CC BY"
    builder.root_node = root
    builder.channel["root_id"] = root["id"]

    # Video node (was "c1")
    video = builder.contentnode_data(
        node_id="32a941fb77c2576e8f6b294cde4c3b0c",
        content_id="c6f49ea527824f398f4d5d26faf19396",
        parent_id=root["id"],
        kind=content_kinds.VIDEO
    )
    video.update({
        "title": "Introduction to Algebra",
        "description": "Learn fundamental algebraic concepts including variables, expressions, and basic equation solving",
        "license_name": "CC BY",
        "author": "Kolibri Content Team",
    })
    # Add files for video
    localfile_high = builder.localfile_data()
    localfile_high["id"] = "9f9438fe6b0d42dd8e913d7d04cfb2b2"
    builder.file_data(
        video["id"],
        localfile_high["id"],
        preset=format_presets.VIDEO_HIGH_RES
    )
    localfile_low = builder.localfile_data()
    localfile_low["id"] = "725257a0570044acbd59f8cf6a68b2be"
    builder.file_data(
        video["id"],
        localfile_low["id"],
        preset=format_presets.VIDEO_LOW_RES
    )

    # Topic node (was "c2")
    topic = builder.contentnode_data(
        node_id="2e8bac07947855369fe2d77642dfc870",
        content_id="1fe38e5af42f42678f8db66a18f8267a",
        parent_id=root["id"],
        kind=content_kinds.TOPIC
    )
    topic.update({
        "title": "Advanced Mathematics",
        "description": "Collection of advanced mathematics learning resources including exercises and reference materials",
        "license_name": "CC BY-SA",
        "author": "Educational Content Creators",
    })

    # Exercise node (was "c2c1")
    exercise = builder.contentnode_data(
        node_id="2b6926ed22025518a8b9da91745b51d3",
        content_id="ce603df7c46b424b934348995e1b05fb",
        parent_id=topic["id"],
        kind=content_kinds.EXERCISE
    )
    exercise.update({
        "title": "Linear Equations Practice",
        "description": "Practice problems for solving single-variable linear equations with step-by-step guidance",
        "license_name": "CC BY",
        "author": "Learning Equity",
    })
    # Add files for exercise
    localfile_ex = builder.localfile_data()
    localfile_ex["id"] = "e00699f859624e0f875ac6fe1e13d648"
    builder.file_data(
        exercise["id"],
        localfile_ex["id"],
        preset=format_presets.EXERCISE
    )
    localfile_ex2 = builder.localfile_data(extension="mp3")
    localfile_ex2["id"] = "4c30dc7619f74f97ae2ccd4fffd09bf2"
    builder.file_data(
        exercise["id"],
        localfile_ex2["id"],
        preset=format_presets.EXERCISE
    )
    # Add caption file
    localfile_caption = builder.localfile_data(extension="vtt")
    localfile_caption["id"] = "8ad3fffedf144cba9492e16daec1e39a"
    builder.file_data(
        exercise["id"],
        localfile_caption["id"],
        supplementary=True,
        preset="caption"
    )

    # Document node (was "c2c2")
    document = builder.contentnode_data(
        node_id="4d0c890de9b65d6880ccfa527800e0f4",
        content_id="481e1bda1faa445d801ceb2afbd2f42f",
        parent_id=topic["id"],
        kind=content_kinds.DOCUMENT
    )
    document.update({
        "title": "Algebra Study Guide",
        "description": "Comprehensive reference material covering algebraic principles and problem-solving strategies",
        "license_name": "CC BY-SA",
        "author": "Open Education Resources",
    })

    # Audio node (was "c2c3")
    audio = builder.contentnode_data(
        node_id="b391bfeec8a458f89f013cf1ca9cf33a",
        content_id="f2332710c2fd483386cdeb5ecbdda81f",
        parent_id=topic["id"],
        kind=content_kinds.AUDIO
    )
    audio.update({
        "title": "Mathematics Podcast",
        "description": "Audio discussion of mathematical problem-solving techniques and strategies",
        "license_name": "CC BY-NC",
        "author": "Educational Content Creators",
    })

    # Audio node without license (was "no_license")
    audio_no_license = builder.contentnode_data(
        node_id="b391bfeec8a458f89f013cf1ca9cf331",
        content_id="f2332710c2fd483386cdeb5ecbdda81e",
        parent_id=root["id"],
        kind=content_kinds.AUDIO
    )
    audio_no_license.update({
        "title": "Sample Audio Resource",
        "description": "Audio content for testing license validation and edge cases",
        "license_name": None,
        "author": "",
    })

    # Build tree structure
    topic["children"] = [exercise, document, audio]
    root["children"] = [video, topic, audio_no_license]

    # Create tags
    tag_mathematics = builder.tag_data("mathematics")
    tag_algebra = builder.tag_data("algebra")
    tag_educational = builder.tag_data("educational")

    # Assign tags to nodes (to match old fixture structure)
    # Root has 3 tags
    builder.add_tag_to_node(root["id"], tag_mathematics["id"])
    builder.add_tag_to_node(root["id"], tag_algebra["id"])
    builder.add_tag_to_node(root["id"], tag_educational["id"])

    # Video has 1 tag
    builder.add_tag_to_node(video["id"], tag_algebra["id"])

    # Topic has 1 tag
    builder.add_tag_to_node(topic["id"], tag_mathematics["id"])

    # Generate Django model instances
    builder.generate_nodes_from_root_node()

    return builder
