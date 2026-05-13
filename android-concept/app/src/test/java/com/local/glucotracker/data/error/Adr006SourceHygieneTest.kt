package com.local.glucotracker.data.error

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Test

class Adr006SourceHygieneTest {
    @Test
    fun composablesUseLifecycleAwareFlowCollection() {
        val offenders = sourceFilesUnder("src/main/java")
            .filter { it.readText().contains(Regex("""\.collectAsState\(""")) }
            .map { it.invariantSeparatorsPath }

        assertEquals(emptyList<String>(), offenders)
    }

    @Test
    fun outboxStateDoesNotContainClientSideEstimating() {
        val offenders = sourceFilesUnder("src/main/java")
            .filterNot { it.invariantSeparatorsPath.endsWith("DatabaseModule.kt") }
            .filterNot { it.invariantSeparatorsPath.endsWith("Entities.kt") }
            .filter { it.readText().contains("OutboxState.Estimating") }
            .map { it.invariantSeparatorsPath }

        assertEquals(emptyList<String>(), offenders)
    }

    private fun sourceFilesUnder(path: String): List<File> =
        File(path).walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .toList()
}
