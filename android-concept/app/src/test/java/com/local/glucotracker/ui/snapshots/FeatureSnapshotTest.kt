package com.local.glucotracker.ui.snapshots

import app.cash.paparazzi.Paparazzi
import com.local.glucotracker.ui.design.GT
import kotlinx.datetime.LocalTime
import org.junit.Rule
import org.junit.Test

class FeatureSnapshotTest {
    @get:Rule
    val paparazzi = Paparazzi()

    @Test
    fun foodTodayOverGoal() {
        paparazzi.snapshotThemed("food_today_over_goal") {
            TodaySnapshot(
                state = foodTodayOverGoalState(),
                brandAccentColor = GT.colors.warn,
                now = LocalTime(18, 0),
            )
        }
    }

    @Test
    fun foodTodayUnderGoal() {
        paparazzi.snapshotThemed("food_today_under_goal") {
            TodaySnapshot(
                state = foodTodayUnderGoalState(),
                brandAccentColor = GT.colors.warn,
                now = LocalTime(18, 0),
            )
        }
    }

    @Test
    fun foodTodayOnTarget() {
        paparazzi.snapshotThemed("food_today_on_target") {
            TodaySnapshot(
                state = foodTodayOnTargetState(),
                brandAccentColor = GT.colors.warn,
                now = LocalTime(18, 0),
            )
        }
    }

    @Test
    fun foodTodayEarlyMorning() {
        paparazzi.snapshotThemed("food_today_early_morning") {
            TodaySnapshot(
                state = foodTodayOverGoalState(),
                brandAccentColor = GT.colors.warn,
                now = LocalTime(8, 30),
            )
        }
    }

    @Test
    fun foodTodayNoGoal() {
        paparazzi.snapshotThemed("food_today_no_goal") {
            TodaySnapshot(
                state = foodTodayNoGoalState(),
                brandAccentColor = GT.colors.warn,
                now = LocalTime(18, 0),
            )
        }
    }
}
