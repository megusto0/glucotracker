package com.local.glucotracker.ui.snapshots

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.glucose.GlucoseSurfaces
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

object SnapshotGlucoseSurfaces : GlucoseSurfaces {
    @Composable
    override fun MiniGlucoseCard(modifier: Modifier) {
        GTHintBox(
            text = stringResource(R.string.today_glucose_no_fresh),
            modifier = modifier,
        )
    }

    @Composable
    override fun StatsTirSection() {
        GTHintBox(text = stringResource(R.string.stats_tir_empty))
    }

    @Composable
    override fun StatsDaypartSection() {
        GTHintBox(text = stringResource(R.string.stats_daypart_caption))
    }

    @Composable
    override fun RecordGlucoseAtMealPanel(eatenAt: Instant) {
        GTHintBox(text = stringResource(R.string.record_glucose_at, "09:15"))
    }

    @Composable
    override fun HistoryDayCgmSparkline(date: LocalDate) {
        GTHintBox(
            text = stringResource(R.string.history_filter_cgm),
            modifier = Modifier.padding(start = 10.dp),
        )
    }

    @Composable
    override fun MoreNightscoutSection() {
        Column {
            GTHintBox(text = stringResource(R.string.more_ns_connected))
            GTHairlineDivider()
        }
    }
}
