package com.local.glucotracker.ui.format

/**
 * A package spec at the end of a product's name: «2x64 г», «500 г», «1 л».
 *
 * Anchored to the end, because that is where a shop puts it and where it is
 * safely detachable. A size in the middle of a name is usually load-bearing —
 * «Твикс Экстра 82 г с карамелью» is not the same product as «Твикс Экстра».
 */
private val PackSuffix = Regex(
    // An optional count first — «2x», «5пак*» — then the size and its unit.
    // The count carries its own word in «5пак*80г», which is why the unit is
    // allowed to sit between the number and the multiplier.
    """[\s,·-]*\(?""" +
        """(?:\d{1,4}(?:[.,]\d+)?\s*(?:пак|шт|уп)?\s*[x*х×]\s*)?""" +
        // Weights and volumes only. A bare count is not packaging: «Наггетсы
        // (9 Шт)» and «Крылышки (6 Шт)» are different dishes, and trimming the
        // number leaves two rows that claim to be the same thing.
        """\d{1,4}(?:[.,]\d+)?\s*(?:г|гр|кг|мл|л|g|kg|ml|l)\.?\)?$""",
    RegexOption.IGNORE_CASE,
)

/** A leading count, as «2x64 г» is sometimes written «2 x 64 г Пончики». */
private val LeadingCount = Regex("""^\s*\d{1,2}\s*[x*х×]\s*""", RegexOption.IGNORE_CASE)

/**
 * The product's name without the package it came in.
 *
 * A diary row already says how much was eaten, right beside the name, so a
 * name that also carries «2x64 г» contradicts it: half a doughnut was logged
 * and the line read like a whole two-pack. The stored entry keeps the original
 * — a record of what was bought should not be rewritten by a later idea about
 * display — so this is only ever applied on the way to the screen.
 *
 * Trims at most one spec, and never the whole name: «500 г» on its own stays
 * as it is, because a name is more useful than nothing.
 */
fun productNameWithoutPack(name: String): String {
    val withoutLeading = LeadingCount.replace(name.trim(), "")
    val trimmed = PackSuffix.replace(withoutLeading, "").trim().trimEnd(',', '·', '-', '(')
    return trimmed.ifBlank { name.trim() }
}
