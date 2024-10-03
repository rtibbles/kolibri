# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-12-19 02:29
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("content", "0024_channelmetadata_public")]

    operations = [
        migrations.AlterField(
            model_name="contentnode",
            name="kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("topic", "Topic"),
                    ("video", "Video"),
                    ("audio", "Audio"),
                    ("exercise", "Exercise"),
                    ("document", "Document"),
                    ("html5", "HTML5 App"),
                    ("slideshow", "Slideshow"),
                    ("h5p", "H5P"),
                ],
                max_length=200,
            ),
        )
    ]
