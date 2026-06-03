package com.local.glucotracker.ui.feature.more

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.local.glucotracker.BuildConfig
import com.local.glucotracker.R
import com.local.glucotracker.data.settings.NotificationToggles
import com.local.glucotracker.domain.model.UserGoals
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTSectionLabel
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import kotlin.math.max

@Composable
fun MoreRoute(
    onOpenBase: () -> Unit,
    onOpenOutbox: () -> Unit,
    brandAccentColor: Color? = null,
    viewModel: MoreViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    MoreScreen(
        state = state,
        onOpenBase = onOpenBase,
        onOpenOutbox = onOpenOutbox,
        onClearCache = viewModel::clearCache,
        onSaveGoals = viewModel::saveGoals,
        onToggleNotification = viewModel::toggleNotification,
        onSetRhythmOverride = viewModel::setRhythmOverride,
        onClearRhythmOverride = viewModel::clearRhythmOverride,
        onLogout = viewModel::logout,
        brandAccentColor = brandAccentColor,
    )
}

@Composable
fun MoreScreen(
    state: MoreState,
    onOpenBase: () -> Unit,
    onOpenOutbox: () -> Unit,
    onClearCache: () -> Unit,
    onSaveGoals: (
        dailyKcal: String,
        dailyProteinG: String,
        dailyCarbsG: String,
        dailyFatG: String,
        weightKg: String,
    ) -> Unit,
    onToggleNotification: (key: String) -> Unit,
    onSetRhythmOverride: (String) -> Unit,
    onClearRhythmOverride: () -> Unit,
    onLogout: () -> Unit,
    modifier: Modifier = Modifier,
    brandAccentColor: Color? = null,
) {
    var showCacheConfirm by remember { mutableStateOf(false) }
    var showGoalsSheet by remember { mutableStateOf(false) }
    var showLogoutConfirm by remember { mutableStateOf(false) }
    val accent = brandAccentColor ?: GT.colors.info

    if (showCacheConfirm) {
        CacheConfirmSheet(
            onConfirm = {
                onClearCache()
                showCacheConfirm = false
            },
            onDismiss = { showCacheConfirm = false },
        )
    }
    if (showGoalsSheet) {
        GoalsEditSheet(
            goals = state.goals,
            onSave = { kcal, protein, carbs, fat, weight ->
                onSaveGoals(kcal, protein, carbs, fat, weight)
                showGoalsSheet = false
            },
            onDismiss = { showGoalsSheet = false },
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
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        LocalGlucoseSurfaces.current.MoreNightscoutSection()

        DebugHealthConnectSection()

        BaseSection(
            productCount = state.productCount,
            templateCount = state.templateCount,
            onOpenBase = onOpenBase,
        )

        RhythmSection(
            rhythm = state.rhythm,
            accent = accent,
            onSetOverride = onSetRhythmOverride,
            onClearOverride = onClearRhythmOverride,
        )

        GoalsSection(
            goals = state.goals,
            onEdit = { showGoalsSheet = true },
        )

        NotificationsSection(
            notifications = state.notifications,
            accent = accent,
            onToggle = onToggleNotification,
        )

        DataSection(
            cacheSizeLabel = state.cacheSizeLabel,
            outboxCount = state.outboxCount,
            outboxStuckCount = state.outboxStuckCount,
            onOpenOutbox = onOpenOutbox,
            onClearCache = { showCacheConfirm = true },
        )

        ExportSection()
        AboutSection()
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

    SettingsSection(title = stringResource(R.string.more_health_connect_title)) {
        SettingsGroup {
            SettingsRow(
                title = stringResource(R.string.more_health_connect_title),
                description = stringResource(R.string.more_health_connect_hint),
                glyph = SettingsGlyphKind.Signal,
                action = {
                    GTOutlineButton(
                        text = stringResource(R.string.more_health_connect_connect),
                        onClick = {
                            runCatching {
                                Class
                                    .forName(
                                        "com.local.glucotracker.healthconnect.DebugHealthConnectSync",
                                    )
                                    .getMethod("requestSync")
                                    .invoke(null)
                            }
                        },
                    )
                },
            )
        }
    }
}

@Composable
private fun BaseSection(
    productCount: Int,
    templateCount: Int,
    onOpenBase: () -> Unit,
) {
    val meta = if (productCount == 0 && templateCount == 0) {
        stringResource(R.string.more_base_products_meta_empty)
    } else {
        stringResource(R.string.more_base_products_meta, productCount, templateCount)
    }
    SettingsSection(title = stringResource(R.string.more_base_section)) {
        SettingsGroup {
            SettingsRow(
                title = stringResource(R.string.more_base_products_title),
                description = meta,
                glyph = SettingsGlyphKind.Products,
                action = {
                    GTOutlineButton(
                        text = stringResource(R.string.more_base_open),
                        onClick = onOpenBase,
                    )
                },
            )
            GTHairlineDivider()
            SettingsRow(
                title = stringResource(R.string.more_import_title),
                description = stringResource(R.string.more_import_desc),
                glyph = SettingsGlyphKind.Download,
                locked = true,
                action = { DesktopPill() },
            )
        }
    }
}

@Composable
private fun RhythmSection(
    rhythm: RhythmUi?,
    accent: Color,
    onSetOverride: (String) -> Unit,
    onClearOverride: () -> Unit,
) {
    var overrideValue by remember(rhythm?.anchorMinutes) {
        mutableStateOf(rhythm?.anchorMinutes?.minuteLabel().orEmpty())
    }
    val basis = rhythm?.basis ?: stringResource(R.string.value_empty)

    SettingsSection(
        title = stringResource(R.string.more_rhythm_title),
        note = basis,
    ) {
        SettingsGroup {
            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = stringResource(R.string.more_rhythm_override_label),
                        color = GT.colors.muted,
                        style = GT.type.sansLabel,
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        text = rhythm?.anchorMinutes?.minuteLabel()
                            ?: stringResource(R.string.value_empty),
                        color = GT.colors.ink,
                        style = GT.type.monoLabel.copy(fontSize = 13.sp),
                    )
                }

                if (rhythm?.windows.isNullOrEmpty()) {
                    GTHintBox(text = stringResource(R.string.more_rhythm_no_data))
                } else {
                    RhythmBar(windows = rhythm.windows, accent = accent)
                    RhythmLegend(windows = rhythm.windows, accent = accent)
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedTextField(
                        value = overrideValue,
                        onValueChange = {
                            overrideValue = it
                                .filter { char -> char.isDigit() || char == ':' }
                                .take(5)
                        },
                        label = {
                            Text(
                                text = stringResource(R.string.more_rhythm_override_label),
                                color = GT.colors.muted,
                                style = GT.type.sansLabel,
                            )
                        },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        textStyle = GT.type.monoLabel.copy(color = GT.colors.ink),
                        colors = fieldColors(),
                        shape = GT.shapes.tag,
                    )
                    GTOutlineButton(
                        text = stringResource(R.string.record_save),
                        onClick = { onSetOverride(overrideValue) },
                    )
                }

                if (rhythm?.hasOverride == true) {
                    GTOutlineButton(
                        text = stringResource(R.string.more_rhythm_clear),
                        onClick = onClearOverride,
                    )
                }
            }
        }
    }
}

@Composable
private fun GoalsSection(
    goals: UserGoals,
    onEdit: () -> Unit,
) {
    SettingsSection(title = stringResource(R.string.more_section_goals)) {
        SettingsGroup {
            SettingsRow(
                title = stringResource(R.string.more_goals_summary_title),
                description = goals.summaryText(),
                glyph = SettingsGlyphKind.Goal,
                action = {
                    GTOutlineButton(
                        text = stringResource(R.string.more_goals_edit),
                        onClick = onEdit,
                    )
                },
            )
        }
    }
}

@Composable
private fun NotificationsSection(
    notifications: NotificationToggles,
    accent: Color,
    onToggle: (key: String) -> Unit,
) {
    SettingsSection(
        title = stringResource(R.string.more_section_notifications),
        note = stringResource(R.string.more_notif_soft_note),
    ) {
        SettingsGroup {
            NotificationRow(
                title = stringResource(R.string.more_notif_meal_reminder),
                description = stringResource(R.string.more_notif_meal_desc),
                checked = notifications.mealReminder,
                accent = accent,
                onToggle = { onToggle("meal_reminder") },
            )
            GTHairlineDivider()
            NotificationRow(
                title = stringResource(R.string.more_notif_sync_fail),
                description = stringResource(R.string.more_notif_sync_fail_desc),
                checked = notifications.nsFail,
                accent = accent,
                onToggle = { onToggle("ns_fail") },
            )
            GTHairlineDivider()
            NotificationRow(
                title = stringResource(R.string.more_notif_low_confidence),
                description = stringResource(R.string.more_notif_low_confidence_desc),
                checked = notifications.lowConfidence,
                accent = accent,
                onToggle = { onToggle("low_confidence") },
            )
            GTHairlineDivider()
            NotificationRow(
                title = stringResource(R.string.more_notif_outbox_stuck),
                description = stringResource(R.string.more_notif_outbox_stuck_desc),
                checked = notifications.outboxStuck,
                accent = accent,
                onToggle = { onToggle("outbox_stuck") },
            )
        }
    }
}

@Composable
private fun DataSection(
    cacheSizeLabel: String,
    outboxCount: Int,
    outboxStuckCount: Int,
    onOpenOutbox: () -> Unit,
    onClearCache: () -> Unit,
) {
    val outboxMeta = if (outboxCount == 0) {
        stringResource(R.string.more_sync_queue_meta_empty)
    } else {
        stringResource(R.string.more_sync_queue_meta, outboxCount, outboxStuckCount)
    }
    SettingsSection(title = stringResource(R.string.more_data_section)) {
        SettingsGroup {
            SettingsRow(
                title = stringResource(R.string.more_sync_queue_title),
                description = outboxMeta,
                glyph = SettingsGlyphKind.Queue,
                action = {
                    GTOutlineButton(
                        text = stringResource(R.string.more_sync_queue_open),
                        onClick = onOpenOutbox,
                    )
                },
            )
            GTHairlineDivider()
            SettingsRow(
                title = stringResource(R.string.more_section_cache),
                description = stringResource(R.string.more_cache_meta, cacheSizeLabel),
                glyph = SettingsGlyphKind.Cache,
                action = {
                    GTOutlineButton(
                        text = stringResource(R.string.more_cache_clear_short),
                        onClick = onClearCache,
                    )
                },
            )
        }
    }
}

@Composable
private fun ExportSection() {
    SettingsSection(title = stringResource(R.string.more_export_section)) {
        SettingsGroup {
            DesktopOnlyRow(title = stringResource(R.string.more_other_pdf))
            GTHairlineDivider()
            DesktopOnlyRow(title = stringResource(R.string.more_other_txt))
            GTHairlineDivider()
            DesktopOnlyRow(title = stringResource(R.string.more_other_openapi))
        }
    }
}

@Composable
private fun AboutSection() {
    SettingsSection(title = stringResource(R.string.more_about_section)) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(GT.colors.surface2, GT.shapes.card)
                .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                .padding(16.dp),
        ) {
            Text(
                text = stringResource(R.string.app_name),
                color = GT.colors.ink,
                style = GT.type.serifSection.copy(fontSize = 18.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = stringResource(R.string.more_about_body),
                modifier = Modifier.padding(top = 6.dp),
                color = GT.colors.muted,
                style = GT.type.sansBody,
            )
            GTHairlineDivider(modifier = Modifier.padding(top = 12.dp))
            Row(
                modifier = Modifier.padding(top = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(
                        R.string.more_about_version,
                        BuildConfig.VERSION_NAME,
                    ),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = stringResource(R.string.more_about_flavor),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                )
            }
        }
    }
}

@Composable
private fun LogoutSection(onLogout: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = GT.space.touch)
            .clickable(role = Role.Button, onClick = onLogout),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = stringResource(R.string.auth_logout_row),
            color = GT.colors.warn,
            style = GT.type.sansBody.copy(fontSize = 13.sp),
        )
    }
}

@Composable
private fun SettingsSection(
    title: String,
    modifier: Modifier = Modifier,
    note: String? = null,
    content: @Composable () -> Unit,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            GTSectionLabel(text = title)
            if (note != null) {
                Spacer(Modifier.weight(1f))
                Text(
                    text = note,
                    color = GT.colors.muted,
                    style = GT.type.monoLabel.copy(fontSize = 10.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        content()
    }
}

@Composable
private fun SettingsGroup(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface2, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clip(GT.shapes.card),
    ) {
        content()
    }
}

@Composable
private fun SettingsRow(
    title: String,
    description: String? = null,
    glyph: SettingsGlyphKind? = null,
    locked: Boolean = false,
    action: (@Composable () -> Unit)? = null,
    onClick: (() -> Unit)? = null,
) {
    val titleColor = if (locked) GT.colors.muted else GT.colors.ink
    val rowModifier = if (onClick == null) {
        Modifier
    } else {
        Modifier.clickable(role = Role.Button, onClick = onClick)
    }
    Row(
        modifier = rowModifier
            .fillMaxWidth()
            .heightIn(min = 58.dp)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (glyph != null) {
            SettingsGlyph(kind = glyph, muted = locked)
            Spacer(Modifier.width(12.dp))
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                color = titleColor,
                style = GT.type.sansBody.copy(fontSize = 14.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (description != null) {
                Text(
                    text = description,
                    modifier = Modifier.padding(top = 3.dp),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel.copy(fontSize = 11.sp),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (action != null) {
            Spacer(Modifier.width(10.dp))
            action()
        }
    }
}

@Composable
private fun NotificationRow(
    title: String,
    description: String,
    checked: Boolean,
    accent: Color,
    onToggle: () -> Unit,
) {
    SettingsRow(
        title = title,
        description = description,
        action = {
            SettingsSwitch(
                checked = checked,
                accent = accent,
                onToggle = onToggle,
            )
        },
        onClick = onToggle,
    )
}

@Composable
private fun DesktopOnlyRow(title: String) {
    SettingsRow(
        title = title,
        locked = true,
        action = { DesktopPill() },
    )
}

@Composable
private fun DesktopPill() {
    Box(
        modifier = Modifier
            .height(22.dp)
            .background(GT.colors.surface, GT.shapes.tag)
            .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
            .padding(horizontal = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = stringResource(R.string.more_desktop_pill),
            color = GT.colors.muted,
            style = GT.type.sansLabel.copy(fontSize = 9.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun SettingsSwitch(
    checked: Boolean,
    accent: Color,
    onToggle: () -> Unit,
) {
    Box(
        modifier = Modifier
            .heightIn(min = GT.space.touch)
            .width(50.dp)
            .clickable(role = Role.Switch, onClick = onToggle),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .width(46.dp)
                .height(28.dp)
                .background(
                    color = if (checked) accent else GT.colors.hairline2,
                    shape = RoundedCornerShape(14.dp),
                )
                .border(
                    width = GT.space.hairline,
                    color = GT.colors.hairline2.copy(alpha = 0.45f),
                    shape = RoundedCornerShape(14.dp),
                )
                .padding(3.dp),
            contentAlignment = if (checked) Alignment.CenterEnd else Alignment.CenterStart,
        ) {
            Box(
                modifier = Modifier
                    .size(22.dp)
                    .background(GT.colors.surface2, CircleShape),
            )
        }
    }
}

@Composable
private fun RhythmBar(
    windows: List<RhythmWindowUi>,
    accent: Color,
) {
    val colors = listOf(accent, GT.colors.accent, GT.colors.warn, GT.colors.info)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(38.dp)
            .clip(GT.shapes.tag),
    ) {
        windows.forEachIndexed { index, window ->
            val duration = windowDuration(window.startMinute, window.endMinute)
            Box(
                modifier = Modifier
                    .weight(duration.toFloat())
                    .fillMaxHeight()
                    .background(colors[index % colors.size]),
                contentAlignment = Alignment.CenterStart,
            ) {
                Text(
                    text = window.label,
                    modifier = Modifier.padding(horizontal = 7.dp),
                    color = GT.colors.surface2,
                    style = GT.type.sansLabel.copy(fontSize = 9.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun RhythmLegend(
    windows: List<RhythmWindowUi>,
    accent: Color,
) {
    val colors = listOf(accent, GT.colors.accent, GT.colors.warn, GT.colors.info)
    Column {
        windows.forEachIndexed { index, window ->
            if (index > 0) GTHairlineDivider()
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 7.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    modifier = Modifier
                        .size(9.dp)
                        .background(colors[index % colors.size], GT.shapes.iconButton),
                )
                Text(
                    text = window.label,
                    modifier = Modifier
                        .padding(start = 9.dp)
                        .weight(1f),
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = stringResource(
                        R.string.more_rhythm_window,
                        window.startMinute.minuteLabel(),
                        window.endMinute.minuteLabel(),
                    ),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun SettingsGlyph(
    kind: SettingsGlyphKind,
    muted: Boolean,
) {
    val color = if (muted) GT.colors.muted else GT.colors.ink2
    Box(
        modifier = Modifier.width(30.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.size(18.dp)) {
            val stroke = Stroke(width = 1.4.dp.toPx(), cap = StrokeCap.Round)
            when (kind) {
                SettingsGlyphKind.Products -> {
                    drawRoundRect(
                        color = color,
                        style = stroke,
                        cornerRadius = CornerRadius(2.dp.toPx()),
                    )
                    drawLine(color, Offset(4.dp.toPx(), 6.dp.toPx()), Offset(14.dp.toPx(), 6.dp.toPx()), strokeWidth = 1.2.dp.toPx())
                    drawLine(color, Offset(4.dp.toPx(), 9.dp.toPx()), Offset(14.dp.toPx(), 9.dp.toPx()), strokeWidth = 1.2.dp.toPx())
                    drawLine(color, Offset(4.dp.toPx(), 12.dp.toPx()), Offset(10.dp.toPx(), 12.dp.toPx()), strokeWidth = 1.2.dp.toPx())
                }
                SettingsGlyphKind.Download -> {
                    drawLine(color, Offset(9.dp.toPx(), 3.dp.toPx()), Offset(9.dp.toPx(), 11.dp.toPx()), strokeWidth = 1.4.dp.toPx(), cap = StrokeCap.Round)
                    drawLine(color, Offset(6.dp.toPx(), 8.dp.toPx()), Offset(9.dp.toPx(), 11.dp.toPx()), strokeWidth = 1.4.dp.toPx(), cap = StrokeCap.Round)
                    drawLine(color, Offset(12.dp.toPx(), 8.dp.toPx()), Offset(9.dp.toPx(), 11.dp.toPx()), strokeWidth = 1.4.dp.toPx(), cap = StrokeCap.Round)
                    drawLine(color, Offset(4.dp.toPx(), 14.dp.toPx()), Offset(14.dp.toPx(), 14.dp.toPx()), strokeWidth = 1.4.dp.toPx(), cap = StrokeCap.Round)
                }
                SettingsGlyphKind.Goal -> {
                    drawCircle(color = color, radius = 7.dp.toPx(), style = stroke)
                    drawCircle(color = color, radius = 2.dp.toPx())
                }
                SettingsGlyphKind.Queue -> {
                    drawCircle(color = color, radius = 2.dp.toPx(), center = Offset(5.dp.toPx(), 6.dp.toPx()))
                    drawLine(color, Offset(9.dp.toPx(), 6.dp.toPx()), Offset(15.dp.toPx(), 6.dp.toPx()), strokeWidth = 1.4.dp.toPx(), cap = StrokeCap.Round)
                    drawCircle(color = color, radius = 2.dp.toPx(), center = Offset(5.dp.toPx(), 12.dp.toPx()))
                    drawLine(color, Offset(9.dp.toPx(), 12.dp.toPx()), Offset(15.dp.toPx(), 12.dp.toPx()), strokeWidth = 1.4.dp.toPx(), cap = StrokeCap.Round)
                }
                SettingsGlyphKind.Cache -> {
                    drawRoundRect(
                        color = color,
                        topLeft = Offset(3.dp.toPx(), 4.dp.toPx()),
                        size = androidx.compose.ui.geometry.Size(12.dp.toPx(), 12.dp.toPx()),
                        cornerRadius = CornerRadius(2.dp.toPx()),
                        style = stroke,
                    )
                    drawLine(color, Offset(6.dp.toPx(), 8.dp.toPx()), Offset(12.dp.toPx(), 8.dp.toPx()), strokeWidth = 1.2.dp.toPx())
                    drawLine(color, Offset(6.dp.toPx(), 11.dp.toPx()), Offset(10.dp.toPx(), 11.dp.toPx()), strokeWidth = 1.2.dp.toPx())
                }
                SettingsGlyphKind.Signal -> {
                    drawCircle(color = color, radius = 2.dp.toPx(), center = Offset(9.dp.toPx(), 11.dp.toPx()))
                    drawArc(color, 210f, 120f, false, style = stroke)
                    drawArc(
                        color = color,
                        startAngle = 220f,
                        sweepAngle = 100f,
                        useCenter = false,
                        topLeft = Offset(3.dp.toPx(), 3.dp.toPx()),
                        size = androidx.compose.ui.geometry.Size(12.dp.toPx(), 12.dp.toPx()),
                        style = stroke,
                    )
                }
            }
        }
    }
}

private enum class SettingsGlyphKind {
    Products,
    Download,
    Goal,
    Queue,
    Cache,
    Signal,
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GoalsEditSheet(
    goals: UserGoals,
    onSave: (String, String, String, String, String) -> Unit,
    onDismiss: () -> Unit,
) {
    var kcal by remember(goals) { mutableStateOf(goals.dailyKcal?.toString().orEmpty()) }
    var protein by remember(goals) {
        mutableStateOf(goals.dailyProteinG?.toString().orEmpty())
    }
    var carbs by remember(goals) { mutableStateOf(goals.dailyCarbsG?.toString().orEmpty()) }
    var fat by remember(goals) { mutableStateOf(goals.dailyFatG?.toString().orEmpty()) }
    var weight by remember(goals) { mutableStateOf(goals.weightKg?.toString().orEmpty()) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(),
        containerColor = GT.colors.surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.more_goals_sheet_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            GoalTextField(
                label = stringResource(R.string.more_goals_kcal),
                value = kcal,
                onValueChange = { kcal = it },
                keyboardType = KeyboardType.Number,
            )
            GoalTextField(
                label = stringResource(R.string.more_goals_protein),
                value = protein,
                onValueChange = { protein = it },
                keyboardType = KeyboardType.Number,
            )
            GoalTextField(
                label = stringResource(R.string.more_goals_carbs),
                value = carbs,
                onValueChange = { carbs = it },
                keyboardType = KeyboardType.Number,
            )
            GoalTextField(
                label = stringResource(R.string.more_goals_fat),
                value = fat,
                onValueChange = { fat = it },
                keyboardType = KeyboardType.Number,
            )
            GoalTextField(
                label = stringResource(R.string.more_goals_weight),
                value = weight,
                onValueChange = { weight = it },
                keyboardType = KeyboardType.Decimal,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                GTOutlineButton(
                    text = stringResource(R.string.more_cache_cancel),
                    onClick = onDismiss,
                )
                GTOutlineButton(
                    text = stringResource(R.string.record_save),
                    onClick = { onSave(kcal, protein, carbs, fat, weight) },
                )
            }
        }
    }
}

@Composable
private fun GoalTextField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    keyboardType: KeyboardType,
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
        colors = fieldColors(),
        shape = GT.shapes.tag,
    )
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
                GTOutlineButton(
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
                GTOutlineButton(
                    text = stringResource(R.string.auth_logout_confirm),
                    onClick = onConfirm,
                )
            }
        }
    }
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = GT.colors.ink,
    unfocusedBorderColor = GT.colors.hairline2,
    cursorColor = GT.colors.ink,
)

@Composable
private fun UserGoals.summaryText(): String =
    stringResource(
        R.string.more_goals_summary_meta,
        dailyKcal.valueText(),
        dailyProteinG.valueText(),
        dailyFatG.valueText(),
        dailyCarbsG.valueText(),
    )

@Composable
private fun Int?.valueText(): String =
    this?.toString() ?: stringResource(R.string.value_empty)

private fun Int.minuteLabel(): String {
    val normalized = ((this % 1440) + 1440) % 1440
    val hours = (normalized / 60).toString().padStart(2, '0')
    val minutes = (normalized % 60).toString().padStart(2, '0')
    return "$hours:$minutes"
}

private fun windowDuration(startMinute: Int, endMinute: Int): Int {
    val duration = if (endMinute >= startMinute) {
        endMinute - startMinute
    } else {
        1440 - startMinute + endMinute
    }
    return max(duration, 1)
}
