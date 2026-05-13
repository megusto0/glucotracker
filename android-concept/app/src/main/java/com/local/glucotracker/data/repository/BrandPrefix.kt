package com.local.glucotracker.data.repository

enum class BrandPrefix {
    Bk,
    Mc,
    Kfc,
    Restaurant,
    Product,
    Template,
}

fun parsePrefix(text: String): Pair<BrandPrefix?, String> {
    val colon = text.indexOf(':')
    if (colon <= 0) return null to text

    val token = text.substring(0, colon).lowercase()
    val prefix = when (token) {
        "bk" -> BrandPrefix.Bk
        "mc" -> BrandPrefix.Mc
        "kfc" -> BrandPrefix.Kfc
        "r" -> BrandPrefix.Restaurant
        "p" -> BrandPrefix.Product
        "t" -> BrandPrefix.Template
        else -> null
    }

    return if (prefix == null) {
        null to text
    } else {
        prefix to text.substring(colon + 1).trimStart()
    }
}
