package com.local.glucotracker.ui.feature.more

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.NightscoutConnectionState
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton
import kotlinx.datetime.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Composable
fun MoreRoute(
    onOpenBase: () -> Unit,
    viewModel: MoreViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    MoreScreen(
        state = state,
        onSyncNightscoutNow = viewModel::syncNightscoutNow,
        onOpenBase = onOpenBase,
        onClearCache = viewModel::clearCache,
        onUpdateGoal = viewModel::updateGoal,
        onToggleNotification = viewModel::toggleNotification,
    )
}

@Composable
fun MoreScreen(
    state: MoreState,
    onSyncNightscoutNow: () -> Unit,
    onOpenBase: () -> Unit,
    onClearCache: () -> Unit,
    onUpdateGoal: (field: String, value: String) -> Unit,
    onToggleNotification: (key: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var showCacheConfirm by remember { mutableStateOf(false) }

    if (showCacheConfirm) {
        CacheConfirmSheet(
            onConfirm = {
                onClearCache()
                showCacheConfirm = false
            },
            onDismiss = { showCacheConfirm = false },
        )
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        NightscoutSection(
            state = state,
            onSyncNow = onSyncNightscoutNow,
        )
        GTHairlineDivider()

        BaseSection(onOpenBase = onOpenBase)
        GTHairlineDivider()

        CacheSection(
            cacheSizeLabel = state.cacheSizeLabel,
            onClearCache = { showCacheConfirm = true },
        )
        GTHairlineDivider()

        GoalsSection(
            goals = state.goals,
            onUpdateGoal = onUpdateGoal,
        )
        GTHairlineDivider()

        AppearanceSection(
            uiPrefs = state.uiPrefs,
        )
        GTHairlineDivider()

        NotificationsSection(
            notifications = state.notifications,
            onToggle = onToggleNotification,
        )
        GTHairlineDivider()

        OtherSection()

        Spacer(Modifier.height(10.dp))
    }
}

@Composable
private fun NightscoutSection(
    state: MoreState,
    onSyncNow: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_nightscout))
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            val connected = state.nightscoutStatus.connectionState == NightscoutConnectionState.Connected
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(
                        if (connected) GT.colors.good else GT.colors.muted,
                        CircleShape,
                    ),
            )
            Text(
                text = nightscoutStatusLabel(state, connected),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            Spacer(Modifier.weight(1f))
            state.nightscoutStatus.lastSyncAt?.let { syncAt ->
                Text(
                    text = formatTimestamp(syncAt),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                )
            }
        }
        if (state.nightscoutStatus.queueDepth > 0) {
            Text(
                text = stringResource(R.string.more_ns_unsynced, state.nightscoutStatus.queueDepth),
                color = GT.colors.warn,
                style = GT.type.monoLabel,
            )
        }
        GTOutlineButton(
            text = if (state.isNightscoutRefreshing) {
                stringResource(R.string.more_ns_checking)
            } else {
                stringResource(R.string.more_ns_sync_now)
            },
            onClick = onSyncNow,
            enabled = !state.isNightscoutRefreshing,
        )
        GTHintBox(text = stringResource(R.string.more_ns_hint))
    }
}

@Composable
private fun nightscoutStatusLabel(
    state: MoreState,
    connected: Boolean,
): String =
    when {
        state.isNightscoutRefreshing -> stringResource(R.string.more_ns_checking)
        connected -> stringResource(R.string.more_ns_connected)
        else -> stringResource(R.string.more_ns_disconnected)
    }

@Composable
private fun BaseSection(onOpenBase: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = stringResource(R.string.base_title))
            Spacer(Modifier.weight(1f))
            GTOutlineButton(
                text = stringResource(R.string.more_base_open),
                onClick = onOpenBase,
            )
        }
        GTHintBox(text = stringResource(R.string.base_desktop_hint))
    }
}

@Composable
private fun CacheSection(
    cacheSizeLabel: String,
    onClearCache: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_cache))
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.more_cache_size, cacheSizeLabel),
                color = GT.colors.ink2,
                style = GT.type.monoLabel,
            )
            Spacer(Modifier.weight(1f))
            GTOutlineButton(
                text = stringResource(R.string.more_cache_clear),
                onClick = onClearCache,
            )
        }
    }
}

@Composable
private fun GoalsSection(
    goals: com.local.glucotracker.domain.model.UserGoals,
    onUpdateGoal: (field: String, value: String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_goals))
        GoalField(
            label = stringResource(R.string.more_goals_kcal),
            value = goals.dailyKcal?.toString().orEmpty(),
            keyboardType = KeyboardType.Number,
            onValueChange = { onUpdateGoal("dailyKcal", it) },
        )
        GoalField(
            label = stringResource(R.string.more_goals_carbs),
            value = goals.dailyCarbsG?.toString().orEmpty(),
            keyboardType = KeyboardType.Number,
            onValueChange = { onUpdateGoal("dailyCarbsG", it) },
        )
        GoalField(
            label = stringResource(R.string.more_goals_weight),
            value = goals.weightKg?.toString().orEmpty(),
            keyboardType = KeyboardType.Decimal,
            onValueChange = { onUpdateGoal("weightKg", it) },
        )
    }
}

@Composable
private fun GoalField(
    label: String,
    value: String,
    keyboardType: KeyboardType,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = {
            Text(
                text = label,
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        },
        modifier = Modifier.fillMaxWidth(),
        textStyle = GT.type.monoLabel.copy(color = GT.colors.ink),
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        singleLine = true,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = GT.colors.ink,
            unfocusedBorderColor = GT.colors.hairline2,
            cursorColor = GT.colors.ink,
        ),
        shape = GT.shapes.tag,
    )
}

@Composable
private fun AppearanceSection(
    uiPrefs: com.local.glucotracker.domain.model.UiPrefs,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_appearance))
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.more_appearance_mono_numbers),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
                modifier = Modifier.weight(1f),
            )
            Switch(
                checked = uiPrefs.useCompactRows,
                onCheckedChange = {},
                colors = SwitchDefaults.colors(
                    checkedTrackColor = GT.colors.accent,
                    checkedBorderColor = GT.colors.accent,
                ),
            )
        }
    }
}

@Composable
private fun NotificationsSection(
    notifications: com.local.glucotracker.data.settings.NotificationToggles,
    onToggle: (key: String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_notifications))
        NotificationRow(
            label = stringResource(R.string.more_notif_meal_reminder),
            checked = notifications.mealReminder,
            onCheckedChange = { onToggle("meal_reminder") },
        )
        NotificationRow(
            label = stringResource(R.string.more_notif_ns_fail),
            checked = notifications.nsFail,
            onCheckedChange = { onToggle("ns_fail") },
        )
        NotificationRow(
            label = stringResource(R.string.more_notif_low_confidence),
            checked = notifications.lowConfidence,
            onCheckedChange = { onToggle("low_confidence") },
        )
        NotificationRow(
            label = stringResource(R.string.more_notif_estimate_ready),
            checked = notifications.estimateReady,
            onCheckedChange = { onToggle("estimate_ready") },
        )
    }
}

@Composable
private fun NotificationRow(
    label: String,
    checked: Boolean,
    onCheckedChange: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = GT.space.touch)
            .clickable(role = Role.Switch, onClick = onCheckedChange)
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            color = GT.colors.ink2,
            style = GT.type.sansBody,
            modifier = Modifier.weight(1f),
        )
        Switch(
            checked = checked,
            onCheckedChange = { onCheckedChange() },
            colors = SwitchDefaults.colors(
                checkedTrackColor = GT.colors.accent,
                checkedBorderColor = GT.colors.accent,
            ),
        )
    }
}

@Composable
private fun OtherSection() {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_other))
        GTHintBox(
            text = "${stringResource(R.string.more_other_pdf)} · ${stringResource(R.string.desktop_only_hint)}",
        )
        GTHintBox(
            text = "${stringResource(R.string.more_other_txt)} · ${stringResource(R.string.desktop_only_hint)}",
        )
        GTHintBox(
            text = "${stringResource(R.string.more_other_openapi)} · ${stringResource(R.string.desktop_only_hint)}",
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CacheConfirmSheet(
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(),
        containerColor = GT.colors.surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = stringResource(R.string.more_cache_confirm_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = stringResource(R.string.more_cache_confirm_body),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                GTOutlineButton(
                    text = stringResource(R.string.more_cache_cancel),
                    onClick = onDismiss,
                )
                GTPrimaryButton(
                    text = stringResource(R.string.more_cache_confirm),
                    onClick = onConfirm,
                )
            }
        }
    }
}

private fun formatTimestamp(instant: Instant): String {
    val dt = instant.toLocalDateTime(TimeZone.currentSystemDefault())
    return "${dt.hour.toString().padStart(2, '0')}:${dt.minute.toString().padStart(2, '0')}"
}
