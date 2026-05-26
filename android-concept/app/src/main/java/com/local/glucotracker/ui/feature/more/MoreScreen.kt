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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces

@Composable
fun MoreRoute(
    onOpenBase: () -> Unit,
    onOpenOutbox: () -> Unit,
    viewModel: MoreViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    MoreScreen(
        state = state,
        onOpenBase = onOpenBase,
        onOpenOutbox = onOpenOutbox,
        onClearCache = viewModel::clearCache,
        onUpdateGoal = viewModel::updateGoal,
        onToggleNotification = viewModel::toggleNotification,
        onSetRhythmOverride = viewModel::setRhythmOverride,
        onClearRhythmOverride = viewModel::clearRhythmOverride,
        onLogout = viewModel::logout,
    )
}

@Composable
fun MoreScreen(
    state: MoreState,
    onOpenBase: () -> Unit,
    onOpenOutbox: () -> Unit,
    onClearCache: () -> Unit,
    onUpdateGoal: (field: String, value: String) -> Unit,
    onToggleNotification: (key: String) -> Unit,
    onSetRhythmOverride: (String) -> Unit,
    onClearRhythmOverride: () -> Unit,
    onLogout: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var showCacheConfirm by remember { mutableStateOf(false) }
    var showLogoutConfirm by remember { mutableStateOf(false) }

    if (showCacheConfirm) {
        CacheConfirmSheet(
            onConfirm = {
                onClearCache()
                showCacheConfirm = false
            },
            onDismiss = { showCacheConfirm = false },
        )
    }
    if (showLogoutConfirm) {
        LogoutConfirmSheet(
            onConfirm = {
                showLogoutConfirm = false
                onLogout()
            },
            onDismiss = { showLogoutConfirm = false },
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
        LocalGlucoseSurfaces.current.MoreNightscoutSection()

        DebugHealthConnectSection()
        GTHairlineDivider()

        BaseSection(onOpenBase = onOpenBase)
        GTHairlineDivider()

        RhythmSection(
            rhythm = state.rhythm,
            onSetOverride = onSetRhythmOverride,
            onClearOverride = onClearRhythmOverride,
        )
        GTHairlineDivider()

        SyncQueueSection(onOpenOutbox = onOpenOutbox)
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
        GTHairlineDivider()

        LogoutSection(onLogout = { showLogoutConfirm = true })

        Spacer(Modifier.height(10.dp))
    }
}

@Composable
private fun DebugHealthConnectSection() {
    val healthConnectAvailable = remember {
        runCatching {
            Class.forName("com.local.glucotracker.healthconnect.DebugHealthConnectSync")
        }.isSuccess
    }
    if (!healthConnectAvailable) return

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = stringResource(R.string.more_health_connect_title))
            Spacer(Modifier.weight(1f))
            GTOutlineButton(
                text = stringResource(R.string.more_health_connect_connect),
                onClick = {
                    runCatching {
                        Class.forName("com.local.glucotracker.healthconnect.DebugHealthConnectSync")
                            .getMethod("requestSync")
                            .invoke(null)
                    }
                },
            )
        }
        GTHintBox(text = stringResource(R.string.more_health_connect_hint))
    }
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
private fun RhythmSection(
    rhythm: RhythmUi?,
    onSetOverride: (String) -> Unit,
    onClearOverride: () -> Unit,
) {
    var overrideValue by remember(rhythm?.anchorMinutes) {
        mutableStateOf(rhythm?.anchorMinutes?.minuteLabel().orEmpty())
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = stringResource(R.string.more_rhythm_title))
            Spacer(Modifier.weight(1f))
            if (rhythm?.hasOverride == true) {
                GTOutlineButton(
                    text = stringResource(R.string.more_rhythm_clear),
                    onClick = onClearOverride,
                )
            }
        }
        Text(
            text = stringResource(
                R.string.more_rhythm_anchor,
                rhythm?.anchorMinutes?.minuteLabel() ?: "—",
                rhythm?.basis ?: "absolute_fallback",
            ),
            color = GT.colors.ink2,
            style = GT.type.sansBody,
        )
        rhythm?.windows.orEmpty().forEach { window ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = window.label,
                    color = GT.colors.ink,
                    style = GT.type.sansLabel,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    text = "${window.startMinute.minuteLabel()}-${window.endMinute.minuteLabel()}",
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(GT.space.sm)) {
            OutlinedTextField(
                value = overrideValue,
                onValueChange = { overrideValue = it.take(5) },
                label = { Text(stringResource(R.string.more_rhythm_override_label)) },
                singleLine = true,
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = GT.colors.ink,
                    unfocusedBorderColor = GT.colors.hairline2,
                    cursorColor = GT.colors.ink,
                ),
                shape = GT.shapes.tag,
            )
            GTOutlineButton(
                text = stringResource(R.string.record_save),
                onClick = { onSetOverride(overrideValue) },
                modifier = Modifier.align(Alignment.CenterVertically),
            )
        }
    }
}

private fun Int.minuteLabel(): String {
    val normalized = ((this % 1440) + 1440) % 1440
    val hours = (normalized / 60).toString().padStart(2, '0')
    val minutes = (normalized % 60).toString().padStart(2, '0')
    return "$hours:$minutes"
}

@Composable
private fun SyncQueueSection(onOpenOutbox: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTKicker(text = stringResource(R.string.more_sync_queue_title))
            Spacer(Modifier.weight(1f))
            GTOutlineButton(
                text = stringResource(R.string.more_sync_queue_open),
                onClick = onOpenOutbox,
            )
        }
        GTHintBox(text = stringResource(R.string.more_sync_queue_hint))
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
            label = stringResource(R.string.more_goals_protein),
            value = goals.dailyProteinG?.toString().orEmpty(),
            keyboardType = KeyboardType.Number,
            onValueChange = { onUpdateGoal("dailyProteinG", it) },
        )
        GoalField(
            label = stringResource(R.string.more_goals_carbs),
            value = goals.dailyCarbsG?.toString().orEmpty(),
            keyboardType = KeyboardType.Number,
            onValueChange = { onUpdateGoal("dailyCarbsG", it) },
        )
        GoalField(
            label = stringResource(R.string.more_goals_fat),
            value = goals.dailyFatG?.toString().orEmpty(),
            keyboardType = KeyboardType.Number,
            onValueChange = { onUpdateGoal("dailyFatG", it) },
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
            label = stringResource(R.string.more_notif_sync_fail),
            checked = notifications.nsFail,
            onCheckedChange = { onToggle("ns_fail") },
        )
        NotificationRow(
            label = stringResource(R.string.more_notif_low_confidence),
            checked = notifications.lowConfidence,
            onCheckedChange = { onToggle("low_confidence") },
        )
        NotificationRow(
            label = stringResource(R.string.more_notif_outbox_stuck),
            checked = notifications.outboxStuck,
            onCheckedChange = { onToggle("outbox_stuck") },
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
    val appName = stringResource(R.string.app_name)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        GTKicker(text = stringResource(R.string.more_section_other))
        OtherHint(text = stringResource(R.string.more_other_pdf))
        OtherHint(text = stringResource(R.string.more_other_txt))
        OtherHint(text = stringResource(R.string.more_other_openapi))
        if (appName == "Tarelka") {
            Text(
                text = stringResource(R.string.more_about_title_tarelka),
                color = GT.colors.ink,
                style = GT.type.sansLabel,
            )
        }
        GTHintBox(text = stringResource(R.string.more_about_body))
    }
}

@Composable
private fun OtherHint(text: String) {
    GTHintBox(text = stringResource(R.string.more_desktop_only_format, text))
}
@Composable
private fun LogoutSection(onLogout: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = GT.space.touch)
            .clickable(role = Role.Button, onClick = onLogout)
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.auth_logout_row),
            color = GT.colors.warn,
            style = GT.type.sansBody,
            modifier = Modifier.weight(1f),
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LogoutConfirmSheet(
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
                text = stringResource(R.string.auth_logout_confirm_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Text(
                text = stringResource(R.string.auth_logout_confirm_body),
                color = GT.colors.ink2,
                style = GT.type.sansBody,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                GTOutlineButton(
                    text = stringResource(R.string.auth_logout_cancel),
                    onClick = onDismiss,
                )
                GTPrimaryButton(
                    text = stringResource(R.string.auth_logout_confirm),
                    onClick = onConfirm,
                )
            }
        }
    }
}
