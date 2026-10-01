"""
Enrich GlucoTracker database with Chef Roll / Twister and piece-based chicken items &
aliases.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import (
    Pattern,
    PatternAlias,
    Product,
    ProductAlias,
    User,
)
from glucotracker.infra.db.session import get_session_factory

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("glucotracker.enrich_data")

# 1. Product definitions to insert/update in `products` (shared/user-accessible)
PRODUCTS_DATA: list[dict[str, Any]] = [
    # Rolls / Twisters
    {
        "name": "Шефролл оригинальный (Твистер)",
        "brand": "Rostic's / KFC",
        "category": "fastfood",
        "icon_emoji": "🌯",
        "default_grams": 184.0,
        "default_serving_text": "1 шт (184 г)",
        "kcal_per_100g": 254.9,
        "protein_per_100g": 12.8,
        "fat_per_100g": 10.7,
        "carbs_per_100g": 27.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 469.0,
        "protein_per_serving": 23.5,
        "fat_per_serving": 19.6,
        "carbs_per_serving": 49.6,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/13802765/d2dc61ddf4ca81120d9bcf199aa1afff/400x400nocrop",
        "aliases": [
            "шефролл",
            "твистер",
            "твистер оригинальный",
            "шефролл оригинальный",
            "шеф ролл",
            "шефролл кфс",
            "твистер кфс",
            "твистер ростикс",
            "шефролл ростикс",
            "twister",
            "shefroll",
        ],
    },
    {
        "name": "Шефролл острый (Твистер острый)",
        "brand": "Rostic's / KFC",
        "category": "fastfood",
        "icon_emoji": "🌯",
        "default_grams": 178.0,
        "default_serving_text": "1 шт (178 г)",
        "kcal_per_100g": 279.2,
        "protein_per_100g": 15.0,
        "fat_per_100g": 12.1,
        "carbs_per_100g": 27.4,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 497.0,
        "protein_per_serving": 26.7,
        "fat_per_serving": 21.6,
        "carbs_per_serving": 48.8,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/13802765/d2dc61ddf4ca81120d9bcf199aa1afff/400x400nocrop",
        "aliases": [
            "шефролл острый",
            "твистер острый",
            "острый твистер",
            "острый шефролл",
            "шеф ролл острый",
            "твистер острый кфс",
            "шефролл острый ростикс",
            "twister spicy",
        ],
    },
    {
        "name": "Шефролл Джуниор (Ай-Твистер)",
        "brand": "Rostic's / KFC",
        "category": "fastfood",
        "icon_emoji": "🌯",
        "default_grams": 130.0,
        "default_serving_text": "1 шт (130 г)",
        "kcal_per_100g": 259.2,
        "protein_per_100g": 12.9,
        "fat_per_100g": 11.0,
        "carbs_per_100g": 27.1,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 337.0,
        "protein_per_serving": 16.8,
        "fat_per_serving": 14.3,
        "carbs_per_serving": 35.2,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/13802765/d2dc61ddf4ca81120d9bcf199aa1afff/400x400nocrop",
        "aliases": [
            "ай твистер",
            "ай-твистер",
            "твистер джуниор",
            "шефролл джуниор",
            "шефролл малый",
            "твистер малый",
            "itwister",
            "i-twister",
        ],
    },
    {
        "name": "Шефролл Де Люкс",
        "brand": "Rostic's / KFC",
        "category": "fastfood",
        "icon_emoji": "🌯",
        "default_grams": 193.0,
        "default_serving_text": "1 шт (193 г)",
        "kcal_per_100g": 256.0,
        "protein_per_100g": 13.7,
        "fat_per_100g": 10.4,
        "carbs_per_100g": 26.9,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 494.0,
        "protein_per_serving": 26.4,
        "fat_per_serving": 20.0,
        "carbs_per_serving": 51.9,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/13802765/d2dc61ddf4ca81120d9bcf199aa1afff/400x400nocrop",
        "aliases": [
            "шефролл делюкс",
            "шефролл де люкс",
            "твистер делюкс",
            "твистер де люкс",
            "твистер делюкс кфс",
        ],
    },
    # Chicken pieces (Wings)
    {
        "name": "Куриные крылышки острые (3 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 75.0,
        "default_serving_text": "3 шт (75 г)",
        "kcal_per_100g": 486.7,
        "protein_per_100g": 31.3,
        "fat_per_100g": 33.2,
        "carbs_per_100g": 15.7,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 365.0,
        "protein_per_serving": 23.5,
        "fat_per_serving": 24.9,
        "carbs_per_serving": 11.8,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/17773786/2dc61ddf4ca81120d9bcf199aa1afff3/400x400nocrop",
        "aliases": [
            "3 крыла",
            "3 крылышка",
            "крылья 3 шт",
            "крылышки 3 шт",
            "3 острых крыла",
            "3 острых крылышка",
            "3 крыла кфс",
            "3 крыла ростикс",
            "3 крылышка кфс",
            "3 wings",
        ],
    },
    {
        "name": "Куриные крылышки острые (5 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 125.0,
        "default_serving_text": "5 шт (125 г)",
        "kcal_per_100g": 486.4,
        "protein_per_100g": 31.3,
        "fat_per_100g": 33.2,
        "carbs_per_100g": 15.7,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 608.0,
        "protein_per_serving": 39.1,
        "fat_per_serving": 41.5,
        "carbs_per_serving": 19.6,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/17773786/2dc61ddf4ca81120d9bcf199aa1afff3/400x400nocrop",
        "aliases": [
            "5 крыльев",
            "5 крылышек",
            "крылья 5 шт",
            "крылышки 5 шт",
            "5 острых крыльев",
            "5 крыльев кфс",
            "5 wings",
        ],
    },
    {
        "name": "Куриные крылышки острые (8 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 200.0,
        "default_serving_text": "8 шт (200 г)",
        "kcal_per_100g": 486.5,
        "protein_per_100g": 31.3,
        "fat_per_100g": 33.2,
        "carbs_per_100g": 15.7,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 973.0,
        "protein_per_serving": 62.6,
        "fat_per_serving": 66.4,
        "carbs_per_serving": 31.4,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/17773786/2dc61ddf4ca81120d9bcf199aa1afff3/400x400nocrop",
        "aliases": [
            "8 крыльев",
            "8 крылышек",
            "крылья 8 шт",
            "крылышки 8 шт",
            "8 острых крыльев",
            "8 крыльев кфс",
            "8 wings",
        ],
    },
    {
        "name": "Куриное крылышко в панировке (1 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 25.0,
        "default_serving_text": "1 шт (25 г)",
        "kcal_per_100g": 324.0,
        "protein_per_100g": 20.8,
        "fat_per_100g": 22.1,
        "carbs_per_100g": 10.4,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 81.0,
        "protein_per_serving": 5.2,
        "fat_per_serving": 5.5,
        "carbs_per_serving": 2.6,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/17773786/2dc61ddf4ca81120d9bcf199aa1afff3/400x400nocrop",
        "aliases": [
            "1 крыло",
            "крыло",
            "1 крылышко",
            "крылышко",
            "куриное крыло",
            "крылышко кфс",
            "острое крыло",
            "1 wing",
        ],
    },
    # Chicken pieces (Legs / Drums)
    {
        "name": "Куриная ножка в панировке (1 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 65.0,
        "default_serving_text": "1 шт (65 г)",
        "kcal_per_100g": 223.1,
        "protein_per_100g": 17.7,
        "fat_per_100g": 13.1,
        "carbs_per_100g": 8.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 145.0,
        "protein_per_serving": 11.5,
        "fat_per_serving": 8.5,
        "carbs_per_serving": 5.2,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "1 ножка",
            "ножка",
            "куриная ножка",
            "голень кфс",
            "ножка кфс",
            "ножка ростикс",
            "1 голень",
            "куриная голень",
            "1 leg",
        ],
    },
    {
        "name": "Куриные ножки в панировке (2 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 130.0,
        "default_serving_text": "2 шт (130 г)",
        "kcal_per_100g": 223.1,
        "protein_per_100g": 17.7,
        "fat_per_100g": 13.1,
        "carbs_per_100g": 8.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 290.0,
        "protein_per_serving": 23.0,
        "fat_per_serving": 17.0,
        "carbs_per_serving": 10.4,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "2 ножки",
            "ножки 2 шт",
            "2 куриные ножки",
            "2 голени",
            "2 ножки кфс",
        ],
    },
    {
        "name": "Куриные ножки в панировке (3 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 195.0,
        "default_serving_text": "3 шт (195 г)",
        "kcal_per_100g": 223.1,
        "protein_per_100g": 17.7,
        "fat_per_100g": 13.1,
        "carbs_per_100g": 8.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 435.0,
        "protein_per_serving": 34.5,
        "fat_per_serving": 25.5,
        "carbs_per_serving": 15.6,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "3 ножки",
            "ножки 3 шт",
            "3 куриные ножки",
            "3 голени",
            "3 ножки кфс",
        ],
    },
    # Strips
    {
        "name": "Стрипсы куриные оригинальные (3 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 100.0,
        "default_serving_text": "3 шт (100 г)",
        "kcal_per_100g": 224.0,
        "protein_per_100g": 20.2,
        "fat_per_100g": 9.4,
        "carbs_per_100g": 14.6,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 224.0,
        "protein_per_serving": 20.2,
        "fat_per_serving": 9.4,
        "carbs_per_serving": 14.6,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "3 стрипса",
            "стрипсы 3 шт",
            "стрипсы 3",
            "3 стрипса кфс",
            "3 стрипса ростикс",
            "стрипсы оригинальные 3 шт",
        ],
    },
    {
        "name": "Стрипсы куриные острые (3 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 100.0,
        "default_serving_text": "3 шт (100 г)",
        "kcal_per_100g": 231.0,
        "protein_per_100g": 20.5,
        "fat_per_100g": 10.1,
        "carbs_per_100g": 14.5,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 231.0,
        "protein_per_serving": 20.5,
        "fat_per_serving": 10.1,
        "carbs_per_serving": 14.5,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "3 острых стрипса",
            "острые стрипсы 3 шт",
            "стрипсы острые 3 шт",
            "3 острых стрипса кфс",
        ],
    },
    {
        "name": "Стрипс куриный (1 шт)",
        "brand": "Rostic's / KFC",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 33.0,
        "default_serving_text": "1 шт (33 г)",
        "kcal_per_100g": 224.0,
        "protein_per_100g": 20.2,
        "fat_per_100g": 9.4,
        "carbs_per_100g": 14.6,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 74.7,
        "protein_per_serving": 6.7,
        "fat_per_serving": 3.1,
        "carbs_per_serving": 4.9,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "1 стрипс",
            "стрипс",
            "куриный стрипс",
            "1 стрипс кфс",
        ],
    },
    # Nuggets
    {
        "name": "Куриные наггетсы (6 шт)",
        "brand": "Rostic's / Вкусно и точка",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 108.0,
        "default_serving_text": "6 шт (108 г)",
        "kcal_per_100g": 261.1,
        "protein_per_100g": 13.9,
        "fat_per_100g": 15.0,
        "carbs_per_100g": 17.2,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 282.0,
        "protein_per_serving": 15.0,
        "fat_per_serving": 16.2,
        "carbs_per_serving": 18.6,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "6 наггетсов",
            "наггетсы 6 шт",
            "наггетсы 6",
            "6 нагетсов",
            "нагетсы 6 шт",
            "6 наггетсов кфс",
        ],
    },
    {
        "name": "Куриные наггетсы (9 шт)",
        "brand": "Rostic's / Вкусно и точка",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 162.0,
        "default_serving_text": "9 шт (162 г)",
        "kcal_per_100g": 261.1,
        "protein_per_100g": 13.9,
        "fat_per_100g": 15.0,
        "carbs_per_100g": 17.2,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 423.0,
        "protein_per_serving": 22.5,
        "fat_per_serving": 24.3,
        "carbs_per_serving": 27.9,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "9 наггетсов",
            "наггетсы 9 шт",
            "наггетсы 9",
            "9 нагетсов",
            "9 наггетсов кфс",
        ],
    },
    {
        "name": "Куриный наггетс (1 шт)",
        "brand": "Rostic's / Вкусно и точка",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 18.0,
        "default_serving_text": "1 шт (18 г)",
        "kcal_per_100g": 261.1,
        "protein_per_100g": 13.9,
        "fat_per_100g": 15.0,
        "carbs_per_100g": 17.2,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 47.0,
        "protein_per_serving": 2.5,
        "fat_per_serving": 2.7,
        "carbs_per_serving": 3.1,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "1 наггетс",
            "наггетс",
            "1 нагетс",
            "нагетс",
            "наггетс 1 шт",
        ],
    },
    # Home-cooked piece chicken
    {
        "name": "Куриная голень запеченная (1 шт)",
        "brand": "Домашняя кухня",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 80.0,
        "default_serving_text": "1 шт (80 г)",
        "kcal_per_100g": 212.5,
        "protein_per_100g": 23.8,
        "fat_per_100g": 13.1,
        "carbs_per_100g": 0.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 170.0,
        "protein_per_serving": 19.0,
        "fat_per_serving": 10.5,
        "carbs_per_serving": 0.0,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "голень куриная запеченная",
            "куриная ножка запеченная",
            "ножка куриная запеченная",
            "куриная ножка жареная",
            "голень куриная 1 шт",
            "1 куриная ножка",
        ],
    },
    {
        "name": "Куриное бедро запеченное (1 шт)",
        "brand": "Домашняя кухня",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 120.0,
        "default_serving_text": "1 шт (120 г)",
        "kcal_per_100g": 216.7,
        "protein_per_100g": 21.7,
        "fat_per_100g": 14.2,
        "carbs_per_100g": 0.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 260.0,
        "protein_per_serving": 26.0,
        "fat_per_serving": 17.0,
        "carbs_per_serving": 0.0,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/15059495/369156d75987dcb3c0af872e5505e94b/400x400nocrop",
        "aliases": [
            "куриное бедро запеченное",
            "бедро куриное запеченное",
            "куриное бедро жареное",
            "бедро куриное 1 шт",
            "1 куриное бедро",
            "1 бедро",
        ],
    },
    {
        "name": "Куриное крылышко запеченное (1 шт)",
        "brand": "Домашняя кухня",
        "category": "meat",
        "icon_emoji": "🍗",
        "default_grams": 35.0,
        "default_serving_text": "1 шт (35 г)",
        "kcal_per_100g": 242.9,
        "protein_per_100g": 27.1,
        "fat_per_100g": 14.9,
        "carbs_per_100g": 0.0,
        "fiber_per_100g": 0.0,
        "kcal_per_serving": 85.0,
        "protein_per_serving": 9.5,
        "fat_per_serving": 5.2,
        "carbs_per_serving": 0.0,
        "fiber_per_serving": 0.0,
        "image_url": "https://avatars.mds.yandex.net/get-eda/17773786/2dc61ddf4ca81120d9bcf199aa1afff3/400x400nocrop",
        "aliases": [
            "куриное крыло запеченное",
            "крыло куриное запеченное",
            "крыло куриное 1 шт",
            "1 куриное крыло",
        ],
    },
]

# 2. Key aliases to enrich on existing `patterns`
PATTERN_EXTRA_ALIASES: dict[str, list[str]] = {
    "shefroll_originalnyi": [
        "шефролл",
        "твистер",
        "твистер оригинальный",
        "шеф ролл",
        "шефролл кфс",
        "твистер кфс",
        "твистер ростикс",
        "шефролл ростикс",
        "twister",
        "shefroll",
    ],
    "shefroll_dzhunior": [
        "ай твистер",
        "ай-твистер",
        "твистер джуниор",
        "шефролл джуниор",
        "шефролл малый",
        "твистер малый",
        "itwister",
        "i-twister",
    ],
    "shefroll_de_lyuks_originalnyi": [
        "шефролл делюкс",
        "шефролл де люкс",
        "твистер делюкс",
        "твистер де люкс",
        "твистер делюкс кфс",
    ],
    "shefroll_de_lyuks_ostryi": [
        "шефролл делюкс острый",
        "твистер делюкс острый",
        "твистер де люкс острый",
        "острый твистер делюкс",
    ],
    "kurinye_krylyshki_3_sht": [
        "3 крыла",
        "3 крылышка",
        "крылья 3 шт",
        "крылышки 3 шт",
        "3 острых крыла",
        "3 острых крылышка",
        "3 крыла кфс",
        "3 крыла ростикс",
        "3 крылышка кфс",
        "3 wings",
    ],
    "kurinye_krylyshki_2_sht": [
        "2 крыла",
        "2 крылышка",
        "крылья 2 шт",
        "крылышки 2 шт",
        "2 острых крыла",
        "2 крыла кфс",
        "2 wings",
    ],
    "kurinye_krylyshki_5_sht": [
        "5 крыльев",
        "5 крылышек",
        "крылья 5 шт",
        "крылышки 5 шт",
        "5 острых крыльев",
        "5 крыльев кфс",
        "5 wings",
    ],
    "kurinye_krylyshki_8_sht": [
        "8 крыльев",
        "8 крылышек",
        "крылья 8 шт",
        "крылышки 8 шт",
        "8 острых крыльев",
        "8 крыльев кфс",
        "8 wings",
    ],
    "kurinye_nozhki_originalnye_1_sht": [
        "ножка",
        "1 ножка",
        "куриная ножка",
        "ножка кфс",
        "ножка ростикс",
        "куриная голень",
        "1 голень",
        "голень кфс",
    ],
    "kurinye_nozhki_originalnye_2_sht": [
        "2 ножки",
        "ножки 2 шт",
        "2 куриные ножки",
        "2 голени",
        "2 ножки кфс",
    ],
    "kurinye_nozhki_originalnye_3_sht": [
        "3 ножки",
        "ножки 3 шт",
        "3 куриные ножки",
        "3 голени",
        "3 ножки кфс",
    ],
    "stripsy_iz_kurinogo_file_originalnye_3_sht": [
        "стрипсы",
        "3 стрипса",
        "стрипсы 3 шт",
        "стрипсы 3",
        "3 стрипса кфс",
        "3 стрипса ростикс",
        "стрипсы оригинальные 3 шт",
    ],
    "stripsy_iz_kurinogo_file_ostrye_3_sht": [
        "острые стрипсы",
        "3 острых стрипса",
        "острые стрипсы 3 шт",
        "стрипсы острые 3 шт",
        "3 острых стрипса кфс",
    ],
    "nuggets_3": [
        "3 наггетса",
        "наггетсы 3 шт",
        "наггетсы 3",
        "3 нагетса",
    ],
    "nuggets_6": [
        "наггетсы",
        "6 наггетсов",
        "наггетсы 6 шт",
        "наггетсы 6",
        "6 нагетсов",
        "нагетсы 6 шт",
        "6 наггетсов кфс",
    ],
    "nuggets_9": [
        "9 наггетсов",
        "наггетсы 9 шт",
        "наггетсы 9",
        "9 нагетсов",
        "нагетсы 9 шт",
        "9 наггетсов кфс",
    ],
    "naggetsy_18_sht": [
        "18 наггетсов",
        "наггетсы 18 шт",
        "наггетсы 18",
        "18 нагетсов",
        "нагетсы 18 шт",
    ],
}


def enrich_database(session: Session) -> None:
    users = session.scalars(select(User)).all()
    user_ids = [u.id for u in users]
    logger.info("Found %d user accounts to enrich", len(user_ids))

    # A. Enrich products and product_aliases for each user (and globally with
    # owner_id=None)
    owners_to_seed = [None, *user_ids]
    added_products = 0
    added_prod_aliases = 0

    for owner_id in owners_to_seed:
        for pdata in PRODUCTS_DATA:
            pname = pdata["name"]
            prod = session.scalar(
                select(Product)
                .where(Product.owner_id == owner_id, Product.name == pname)
                .limit(1)
            )
            if prod is None:
                prod = Product(
                    owner_id=owner_id,
                    name=pname,
                    brand=pdata.get("brand"),
                    category=pdata.get("category"),
                    icon_emoji=pdata.get("icon_emoji"),
                    default_grams=pdata.get("default_grams"),
                    default_serving_text=pdata.get("default_serving_text"),
                    kcal_per_100g=pdata.get("kcal_per_100g"),
                    protein_per_100g=pdata.get("protein_per_100g"),
                    fat_per_100g=pdata.get("fat_per_100g"),
                    carbs_per_100g=pdata.get("carbs_per_100g"),
                    fiber_per_100g=pdata.get("fiber_per_100g"),
                    kcal_per_serving=pdata.get("kcal_per_serving"),
                    protein_per_serving=pdata.get("protein_per_serving"),
                    fat_per_serving=pdata.get("fat_per_serving"),
                    carbs_per_serving=pdata.get("carbs_per_serving"),
                    fiber_per_serving=pdata.get("fiber_per_serving"),
                    image_url=pdata.get("image_url"),
                    source_kind="database_seed",
                )
                session.add(prod)
                session.flush()
                added_products += 1
            else:
                # Update fields if needed
                prod.brand = pdata.get("brand")
                prod.category = pdata.get("category")
                prod.icon_emoji = pdata.get("icon_emoji")
                prod.default_grams = pdata.get("default_grams")
                prod.default_serving_text = pdata.get("default_serving_text")
                prod.kcal_per_100g = pdata.get("kcal_per_100g")
                prod.protein_per_100g = pdata.get("protein_per_100g")
                prod.fat_per_100g = pdata.get("fat_per_100g")
                prod.carbs_per_100g = pdata.get("carbs_per_100g")
                prod.kcal_per_serving = pdata.get("kcal_per_serving")
                prod.protein_per_serving = pdata.get("protein_per_serving")
                prod.fat_per_serving = pdata.get("fat_per_serving")
                prod.carbs_per_serving = pdata.get("carbs_per_serving")
                if pdata.get("image_url") and not prod.image_url:
                    prod.image_url = pdata.get("image_url")
                session.flush()

            # Add product aliases
            for alias_text in pdata.get("aliases", []):
                norm_alias = alias_text.strip().casefold()
                existing_alias = session.scalar(
                    select(ProductAlias)
                    .where(
                        ProductAlias.product_id == prod.id,
                        ProductAlias.alias == norm_alias,
                    )
                    .limit(1)
                )
                if existing_alias is None:
                    session.add(
                        ProductAlias(
                            owner_id=owner_id,
                            product_id=prod.id,
                            alias=norm_alias,
                        )
                    )
                    added_prod_aliases += 1

    session.flush()

    # B. Enrich pattern_aliases on existing patterns in `patterns`
    added_pattern_aliases = 0
    patterns = session.scalars(select(Pattern)).all()
    for pat in patterns:
        key = (pat.key or "").strip().casefold()
        if key in PATTERN_EXTRA_ALIASES:
            for extra_alias in PATTERN_EXTRA_ALIASES[key]:
                norm = extra_alias.strip().casefold()
                existing_pa = session.scalar(
                    select(PatternAlias)
                    .where(
                        PatternAlias.pattern_id == pat.id,
                        PatternAlias.alias == norm,
                    )
                    .limit(1)
                )
                if existing_pa is None:
                    session.add(PatternAlias(pattern_id=pat.id, alias=norm))
                    added_pattern_aliases += 1

    session.commit()
    logger.info(
        "Enrichment completed: %d products created/updated,"
        " %d product aliases added, %d pattern aliases added",
        added_products,
        added_prod_aliases,
        added_pattern_aliases,
    )


def main() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        enrich_database(session)


if __name__ == "__main__":
    main()
