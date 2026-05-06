package com.local.glucotracker.ui.format

import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.extension
import kotlin.io.path.invariantSeparatorsPathString
import kotlin.io.path.readText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NutritionFormatTest {
    @Test
    fun signedKcalUsesTypographicalMinus() {
        assertEquals("−3517", formatSignedKcal(-3517))
    }

    @Test
    fun russianDecimalSeparatorsAreUsed() {
        assertEquals("9,9", formatMmol(9.9))
        assertEquals("72,35", formatKg(72.345))
        assertEquals("44,4", formatGrams(44.4))
        assertEquals("70%", formatPercent(69.6))
    }

    @Test
    fun fixedDecimalFormattingStaysInsideFormatPackage() {
        val sourceRoot = Path.of("src", "main", "java").toAbsolutePath()
        val offenders = Files.walk(sourceRoot).use { paths ->
            paths.iterator().asSequence()
                .filter { it.extension == "kt" }
                .filterNot { it.invariantSeparatorsPathString.contains("/ui/format/") }
                .filter { path ->
                    val text = path.readText()
                    text.contains("String.format") || Regex("%\\.[0-9]+f").containsMatchIn(text)
                }
                .map { sourceRoot.relativize(it).invariantSeparatorsPathString }
                .toList()
        }

        assertTrue("Inline fixed-decimal formatting found: $offenders", offenders.isEmpty())
    }
}
