package com.local.glucotracker.ui.feature.stack

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.add
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.PageSize
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTSectionLabel
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatPercent
import com.local.glucotracker.ui.glucose.LocalGlucoseSurfaces
import com.local.glucotracker.ui.glucose.MealContextAnchor
import com.local.glucotracker.ui.image.rememberApiImageModel
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.absoluteValue
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toJavaLocalDate
import kotlinx.datetime.toLocalDateTime

@Composable
fun MealStackRoute(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: MealStackViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val favoriteFeedback by viewModel.favoriteFeedback.collectAsStateWithLifecycle()
    MealStackScreen(
        state = state,
        favoriteFeedback = favoriteFeedback,
        onBack = onBack,
        onPageChanged = viewModel::onPageChanged,
        onSaveTitle = viewModel::updateTitle,
        onSaveTime = viewModel::updateTime,
        onSaveWeight = viewModel::updateWeight,
        onRetry = viewModel::retryCurrent,
        onFavorite = viewModel::favoriteCurrent,
        onDelete = { viewModel.deleteCurrent(onDeleted = onBack) },
        modifier = modifier,
    )
}

@OptIn(ExperimentalFoundationApi::class, ExperimentalMaterial3Api::class)
@Composable
fun MealStackScreen(
    state: MealStackUiState,
    favoriteFeedback: FavoriteFeedback,
    onBack: () -> Unit,
    onPageChanged: (String) -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onRetry: () -> Unit,
    onFavorite: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
    ) {
        when (state) {
            MealStackUiState.Loading -> StackMessage(text = stringResource(R.string.today_loading))
            is MealStackUiState.Empty -> EmptyStack(date = state.date, onBack = onBack)
            is MealStackUiState.Ready -> ReadyStack(
                state = state,
                favoriteFeedback = favoriteFeedback,
                onBack = onBack,
                onPageChanged = onPageChanged,
                onSaveTitle = onSaveTitle,
                onSaveTime = onSaveTime,
                onSaveWeight = onSaveWeight,
                onRetry = onRetry,
                onFavorite = onFavorite,
                onDelete = onDelete,
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun ReadyStack(
    state: MealStackUiState.Ready,
    favoriteFeedback: FavoriteFeedback,
    onBack: () -> Unit,
    onPageChanged: (String) -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onRetry: () -> Unit,
    onFavorite: () -> Unit,
    onDelete: () -> Unit,
) {
    var editSheetOpen by remember { mutableStateOf(false) }
    val currentCard = state.cards.getOrNull(state.currentIndex)
    val pagerState = rememberPagerState(
        initialPage = state.currentIndex,
        pageCount = { state.cards.size },
    )

    LaunchedEffect(state.currentIndex, state.cards.size) {
        if (state.cards.isNotEmpty() && pagerState.currentPage != state.currentIndex) {
            pagerState.scrollToPage(state.currentIndex)
        }
    }
    LaunchedEffect(pagerState.currentPage, state.cards) {
        state.cards.getOrNull(pagerState.currentPage)?.let { card ->
            onPageChanged(card.id)
        }
    }

    Column(Modifier.fillMaxSize()) {
        StackTopBar(
            date = state.date,
            currentIndex = state.currentIndex,
            total = state.cards.size,
            onBack = onBack,
        )
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalStackGestures(
                    enabled = !editSheetOpen,
                    onOpenEdit = { editSheetOpen = true },
                    onBack = onBack,
                ),
        ) {
            HorizontalPager(
                state = pagerState,
                pageSize = PageSize.Fill,
                contentPadding = PaddingValues(horizontal = 0.dp),
                pageSpacing = 0.dp,
                verticalAlignment = Alignment.CenterVertically,
                userScrollEnabled = state.cards.size > 1 && !editSheetOpen,
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(),
            ) { page ->
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .fillMaxHeight()
                        .padding(bottom = 18.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    MealCardComposable(
                        card = state.cards[page],
                        allCards = state.cards,
                        onRetry = onRetry,
                    )
                }
            }
        }
    }

    if (editSheetOpen && currentCard != null) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false)
        val haptic = LocalHapticFeedback.current
        var hapticReady by remember(currentCard.id) { mutableStateOf(false) }

        LaunchedEffect(sheetState.currentValue) {
            if (
                hapticReady &&
                (
                    sheetState.currentValue == SheetValue.Expanded ||
                        sheetState.currentValue == SheetValue.Hidden
                    )
            ) {
                haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
            }
            hapticReady = true
        }

        ModalBottomSheet(
            onDismissRequest = { editSheetOpen = false },
            sheetState = sheetState,
            shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
            containerColor = GT.colors.bg,
            contentColor = GT.colors.ink,
            tonalElevation = 0.dp,
            scrimColor = Color.Black.copy(alpha = 0.32f),
            dragHandle = { JournalDragHandle() },
            contentWindowInsets = { WindowInsets.ime.add(WindowInsets.navigationBars) },
        ) {
            QuickEditSheet(
                card = currentCard,
                favoriteFeedback = favoriteFeedback,
                onClose = { editSheetOpen = false },
                onSaveTitle = onSaveTitle,
                onSaveTime = onSaveTime,
                onSaveWeight = onSaveWeight,
                onFavorite = onFavorite,
                onDelete = {
                    editSheetOpen = false
                    onDelete()
                },
            )
        }
    }
}

@Composable
private fun StackTopBar(
    date: LocalDate,
    currentIndex: Int,
    total: Int,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val backDescription = stringResource(R.string.stack_back_content_description)
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 10.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = if (total == 1) {
                stringResource(R.string.stack_position_single, stackDate(date))
            } else {
                stringResource(
                    R.string.stack_position,
                    stackDate(date),
                    currentIndex + 1,
                    total,
                )
            },
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 9.sp),
            maxLines = 1,
        )
        StackPageDots(
            currentIndex = currentIndex,
            total = total,
            modifier = Modifier.padding(top = 8.dp),
        )
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(GT.space.touch)
                .clickable(onClick = onBack)
                .semantics { contentDescription = backDescription },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = stringResource(R.string.stack_gesture_back),
                color = GT.colors.muted,
                style = GT.type.kicker.copy(fontSize = 9.sp),
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun StackPageDots(
    currentIndex: Int,
    total: Int,
    modifier: Modifier = Modifier,
) {
    if (total <= 1) return

    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(total) { index ->
            val active = index == currentIndex
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .background(
                        color = if (active) GT.colors.ink else Color.Transparent,
                        shape = CircleShape,
                    )
                    .border(
                        width = GT.space.hairline,
                        color = if (active) GT.colors.ink else GT.colors.hairline2,
                        shape = CircleShape,
                    ),
            )
        }
    }
    Spacer(modifier = Modifier.height(2.dp))
}

@Composable
fun MealCardComposable(
    card: MealCard,
    allCards: List<MealCard> = listOf(card),
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(12.dp)
    Column(
        modifier = modifier
            .width(CardWidth)
            .background(GT.colors.bg, shape)
            .border(1.dp, GT.colors.ink.copy(alpha = 0.22f), shape)
            .padding(start = 12.dp, top = 10.dp, end = 12.dp, bottom = 10.dp),
    ) {
        MealCardPhoto(card = card, onRetry = onRetry)
        Text(
            text = card.title.orEmpty().ifBlank { fallbackTitle(card) },
            modifier = Modifier.padding(top = 10.dp),
            color = GT.colors.ink,
            style = GT.type.serifSection.copy(fontSize = 18.sp, lineHeight = 20.sp),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        StackSubtitleLine(
            card = card,
            modifier = Modifier.padding(top = 4.dp),
        )
        MacrosBlock(
            card = card,
            modifier = Modifier.padding(top = 10.dp),
        )
        MetaBlock(
            card = card,
            allCards = allCards,
            modifier = Modifier.padding(top = 8.dp),
        )
        EditChevron(
            modifier = Modifier
                .padding(top = 4.dp)
                .align(Alignment.CenterHorizontally),
        )
    }
}

@Composable
private fun MealCardPhoto(
    card: MealCard,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val imageModel = rememberApiImageModel(card.photo)
    val shape = RoundedCornerShape(8.dp)
    Box(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(4f / 3f)
            .clip(shape)
            .background(GT.colors.surface)
            .border(GT.space.hairline, GT.colors.hairline2, shape),
        contentAlignment = Alignment.Center,
    ) {
        if (imageModel == null) {
            PhotoPlaceholderGlyph()
        } else {
            AsyncImage(
                model = imageModel,
                contentDescription = null,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        alpha = if (card.state == MealCardState.Confirmed) 1f else 0.5f
                    },
                contentScale = ContentScale.Crop,
            )
        }
        if (card.state != MealCardState.Confirmed) {
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .background(GT.colors.bg.copy(alpha = 0.34f)),
            )
            PendingOverlay(card = card, onRetry = onRetry)
        }
    }
}

@Composable
private fun PendingOverlay(
    card: MealCard,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.padding(10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            text = statusHintText(card),
            color = if (card.state == MealCardState.Stuck) GT.colors.warn else GT.colors.ink2,
            style = GT.type.monoLabel,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        if (card.state == MealCardState.Stuck && (card.outboxId != null || card.serverId != null)) {
            GTOutlineButton(
                text = stringResource(R.string.outbox_retry),
                onClick = onRetry,
            )
        }
    }
}

@Composable
private fun StackSubtitleLine(card: MealCard, modifier: Modifier = Modifier) {
    val separator = stringResource(R.string.stack_subtitle_separator)
    val weight = card.weightGrams?.let { stringResource(R.string.stack_weight_value, formatGrams(it)) }
        ?: stringResource(R.string.stack_weight_value, formatGrams(100.0))
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SubtitleText(text = sourceSubtitleLabel(card.source))
        card.confidence?.let { confidence ->
            SubtitleText(text = separator)
            Box(
                modifier = Modifier
                    .size(5.dp)
                    .background(
                        color = if (confidence < 0.6) GT.colors.warn else GT.colors.accent,
                        shape = CircleShape,
                    ),
            )
            SubtitleText(text = formatPercent(confidence.coerceIn(0.0, 1.0) * 100.0))
        }
        SubtitleText(text = separator)
        SubtitleText(text = weight)
        SubtitleText(text = separator)
        SubtitleText(
            text = card.eatenAt.timeText(),
            modifier = Modifier.weight(1f, fill = false),
        )
    }
}

@Composable
private fun SubtitleText(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        modifier = modifier,
        color = GT.colors.muted,
        style = GT.type.monoLabel.copy(fontSize = 10.sp),
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun EditChevron(modifier: Modifier = Modifier) {
    val description = stringResource(R.string.stack_edit_chevron_content_description)
    val color = GT.colors.muted
    Canvas(
        modifier = modifier
            .size(width = 18.dp, height = 8.dp)
            .semantics { contentDescription = description },
    ) {
        val stroke = 1.2.dp.toPx()
        val y = size.height * 0.68f
        val centerX = size.width / 2f
        drawLine(
            color = color,
            start = Offset(centerX - size.width * 0.28f, y),
            end = Offset(centerX, size.height * 0.28f),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = Offset(centerX, size.height * 0.28f),
            end = Offset(centerX + size.width * 0.28f, y),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun MacrosBlock(card: MealCard, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(GT.colors.surface, RoundedCornerShape(8.dp))
            .padding(horizontal = 4.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        MacroCell(
            label = stringResource(R.string.stack_macro_carbs),
            value = card.carbsG?.let { stringResource(R.string.stack_macro_grams, formatGrams(it)) },
            modifier = Modifier.weight(1f),
        )
        MacroCell(
            label = stringResource(R.string.stack_macro_protein),
            value = card.proteinG?.let { stringResource(R.string.stack_macro_grams, formatGrams(it)) },
            modifier = Modifier.weight(1f),
        )
        MacroCell(
            label = stringResource(R.string.stack_macro_fat),
            value = card.fatG?.let { stringResource(R.string.stack_macro_grams, formatGrams(it)) },
            modifier = Modifier.weight(1f),
        )
        MacroCell(
            label = stringResource(R.string.stack_macro_kcal),
            value = card.kcal?.let { formatKcal(it) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun MacroCell(
    label: String,
    value: String?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = label,
            color = GT.colors.ink2,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            maxLines = 1,
        )
        Text(
            text = value ?: stringResource(R.string.value_empty),
            modifier = Modifier.padding(top = 4.dp),
            color = GT.colors.ink,
            style = GT.type.monoLabel.copy(fontSize = 12.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun MetaBlock(
    card: MealCard,
    allCards: List<MealCard>,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .border(width = 0.dp, color = Color.Transparent),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(GT.space.hairline)
                .background(GT.colors.hairline),
        )
        MetaRow(
            label = stringResource(R.string.stack_meta_source),
            value = sourceMeta(card),
            modifier = Modifier.padding(top = 6.dp),
        )
        LocalGlucoseSurfaces.current.StackMealGlucoseMetaRow(card.eatenAt)
        LocalGlucoseSurfaces.current.StackMealContextMetaRows(
            mealId = card.serverId ?: card.id,
            eatenAt = card.eatenAt,
            meals = allCards.map { meal ->
                MealContextAnchor(
                    id = meal.serverId ?: meal.id,
                    eatenAt = meal.eatenAt,
                )
            },
        )
        if (card.statusHint != MealCardStatusHint.None) {
            MetaRow(
                label = stringResource(R.string.stack_meta_status),
                value = statusHintText(card),
            )
        }
    }
}

@Composable
private fun MetaRow(label: String, value: String, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 8.sp),
            maxLines = 1,
        )
        Text(
            text = value,
            modifier = Modifier.padding(start = 10.dp),
            color = GT.colors.ink2,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun QuickEditSheet(
    card: MealCard,
    favoriteFeedback: FavoriteFeedback,
    onClose: () -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onFavorite: () -> Unit,
    onDelete: () -> Unit,
) {
    var title by remember(card.id, card.title) { mutableStateOf(card.title.orEmpty()) }
    var time by remember(card.id, card.eatenAt) { mutableStateOf(card.eatenAt.timeText()) }
    var weight by remember(card.id, card.weightGrams) { mutableStateOf(editableNumber(card.weightGrams)) }
    val canEditWeight = card.canEditWeight()
    val closeDescription = stringResource(R.string.stack_edit_close)

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .imePadding()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GTIconButton(
                onClick = onClose,
                modifier = Modifier.semantics { contentDescription = closeDescription },
            ) {
                Text(
                    text = "\u00d7",
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel,
                )
            }
            Text(
                text = stringResource(R.string.record_quick_edit),
                modifier = Modifier.padding(start = 8.dp),
                color = GT.colors.ink,
                style = GT.type.serifSection,
                maxLines = 1,
            )
        }
        StackEditField(
            label = stringResource(R.string.record_field_name),
            value = title,
            onValueChange = { title = it },
            actionText = stringResource(R.string.record_save),
            onAction = { onSaveTitle(title) },
        )
        StackEditField(
            label = stringResource(R.string.record_field_time),
            value = time,
            onValueChange = { time = it },
            actionText = stringResource(R.string.record_save),
            onAction = { onSaveTime(time) },
        )
        StackEditField(
            label = stringResource(R.string.record_field_weight),
            value = weight,
            onValueChange = { weight = it },
            actionText = stringResource(R.string.record_recalculate),
            onAction = { onSaveWeight(weight) },
            keyboardType = KeyboardType.Number,
            enabled = canEditWeight,
        )
        if (!canEditWeight) {
            Text(
                text = stringResource(R.string.stack_weight_disabled),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }
        GTHairlineDivider(modifier = Modifier.padding(vertical = 2.dp))
        StackActionsFooter(
            alreadyFavorite = card.primaryProductId != null,
            canFavorite = card.primaryItemId != null,
            favoriteFeedback = favoriteFeedback,
            onFavorite = onFavorite,
            onDelete = onDelete,
        )
    }
}

@Composable
private fun StackActionsFooter(
    alreadyFavorite: Boolean,
    canFavorite: Boolean,
    favoriteFeedback: FavoriteFeedback,
    onFavorite: () -> Unit,
    onDelete: () -> Unit,
) {
    var confirmDelete by remember { mutableStateOf(false) }
    val saved = alreadyFavorite || favoriteFeedback == FavoriteFeedback.Saved
    val favoriteText = when {
        favoriteFeedback == FavoriteFeedback.Saving -> stringResource(R.string.stack_favorite_saving)
        saved -> stringResource(R.string.stack_favorite_saved)
        else -> stringResource(R.string.stack_favorite_add)
    }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            GTOutlineButton(
                text = favoriteText,
                onClick = onFavorite,
                enabled = canFavorite &&
                    !saved &&
                    favoriteFeedback != FavoriteFeedback.Saving,
            )
            Spacer(Modifier.weight(1f))
            Text(
                text = if (confirmDelete) {
                    stringResource(R.string.stack_delete_confirm)
                } else {
                    stringResource(R.string.record_delete)
                },
                modifier = Modifier
                    .heightIn(min = GT.space.touch)
                    .clickable {
                        if (confirmDelete) onDelete() else confirmDelete = true
                    }
                    .padding(horizontal = GT.space.sm, vertical = 12.dp),
                color = GT.colors.warn,
                style = GT.type.sansLabel,
                maxLines = 1,
            )
        }
        val feedbackText = when (favoriteFeedback) {
            FavoriteFeedback.NotEnoughData -> stringResource(R.string.stack_favorite_no_data)
            FavoriteFeedback.Error -> stringResource(R.string.stack_favorite_error)
            else -> null
        }
        if (feedbackText != null) {
            Text(
                text = feedbackText,
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }
    }
}

@Composable
private fun JournalDragHandle() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 10.dp, bottom = 6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(width = 32.dp, height = 4.dp)
                .background(
                    color = GT.colors.muted,
                    shape = RoundedCornerShape(2.dp),
                ),
        )
    }
}

@Composable
private fun StackEditField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    actionText: String,
    onAction: () -> Unit,
    modifier: Modifier = Modifier,
    keyboardType: KeyboardType = KeyboardType.Text,
    enabled: Boolean = true,
) {
    Column(modifier = modifier.fillMaxWidth()) {
        GTSectionLabel(text = label)
        Row(
            modifier = Modifier.padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(GT.space.sm),
        ) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 34.dp)
                    .background(GT.colors.surface2, GT.shapes.tag)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
                    .padding(horizontal = GT.space.sm, vertical = 8.dp),
                contentAlignment = Alignment.CenterStart,
            ) {
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    enabled = enabled,
                    singleLine = true,
                    textStyle = GT.type.sansBody.copy(
                        color = if (enabled) GT.colors.ink else GT.colors.muted,
                    ),
                    cursorBrush = SolidColor(GT.colors.ink),
                    keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            GTOutlineButton(
                text = actionText,
                onClick = onAction,
                enabled = enabled,
            )
        }
    }
}

@Composable
private fun EmptyStack(
    date: LocalDate,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(18.dp),
    ) {
        GTIconButton(onClick = onBack) {
            Text(
                text = "\u2190",
                color = GT.colors.ink2,
                style = GT.type.sansLabel,
            )
        }
        Text(
            text = stackDate(date),
            modifier = Modifier.padding(top = 18.dp),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        Text(
            text = stringResource(R.string.stack_empty),
            modifier = Modifier.padding(top = 10.dp),
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    }
}

@Composable
private fun StackMessage(text: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = GT.colors.muted,
            style = GT.type.sansBody,
        )
    }
}

private fun Modifier.verticalStackGestures(
    enabled: Boolean,
    onOpenEdit: () -> Unit,
    onBack: () -> Unit,
): Modifier =
    if (!enabled) {
        this
    } else {
        pointerInput(Unit) {
            val backThreshold = 44.dp.toPx()
            val editThreshold = -72.dp.toPx()
            val intentSlop = 16.dp.toPx()
            awaitEachGesture {
                val down = awaitFirstDown(requireUnconsumed = false)
                val pointerId = down.id
                var totalX = 0f
                var totalY = 0f
                var handled = false

                while (!handled) {
                    val event = awaitPointerEvent(PointerEventPass.Initial)
                    val change = event.changes.firstOrNull { it.id == pointerId } ?: break
                    if (!change.pressed) break

                    totalX += change.position.x - change.previousPosition.x
                    totalY += change.position.y - change.previousPosition.y

                    val absX = totalX.absoluteValue
                    val absY = totalY.absoluteValue
                    val hasVerticalIntent = absY > intentSlop && absY >= absX * 0.75f
                    if (hasVerticalIntent) {
                        when {
                            totalY > backThreshold -> {
                                handled = true
                                change.consume()
                                onBack()
                            }
                            totalY < editThreshold -> {
                                handled = true
                                change.consume()
                                onOpenEdit()
                            }
                        }
                    }
                }
            }
        }
    }

@Composable
private fun PhotoPlaceholderGlyph() {
    val color = GT.colors.muted
    Canvas(modifier = Modifier.size(38.dp)) {
        drawRoundRect(
            color = color,
            topLeft = Offset(size.width * 0.16f, size.height * 0.18f),
            size = androidx.compose.ui.geometry.Size(size.width * 0.68f, size.height * 0.64f),
            style = Stroke(width = 1.4.dp.toPx()),
        )
        drawCircle(
            color = color,
            radius = size.minDimension * 0.07f,
            center = Offset(size.width * 0.36f, size.height * 0.38f),
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.25f, size.height * 0.7f),
            end = Offset(size.width * 0.45f, size.height * 0.54f),
            strokeWidth = 1.4.dp.toPx(),
        )
        drawLine(
            color = color,
            start = Offset(size.width * 0.45f, size.height * 0.54f),
            end = Offset(size.width * 0.75f, size.height * 0.72f),
            strokeWidth = 1.4.dp.toPx(),
        )
    }
}

@Composable
private fun fallbackTitle(card: MealCard): String =
    if (card.source == MealCardSource.Photo && card.state != MealCardState.Confirmed) {
        stringResource(R.string.today_pending_photo_title)
    } else {
        stringResource(R.string.today_meal_fallback)
    }

@Composable
private fun sourceSubtitleLabel(source: MealCardSource): String =
    when (source) {
        MealCardSource.Photo -> stringResource(R.string.stack_source_photo_estimate)
        MealCardSource.Restaurant -> stringResource(R.string.today_source_restaurant)
        MealCardSource.Pattern -> stringResource(R.string.today_source_pattern)
        MealCardSource.Manual -> stringResource(R.string.today_source_manual)
        MealCardSource.Mixed -> stringResource(R.string.today_source_mixed)
        MealCardSource.Text -> stringResource(R.string.today_source_text)
    }

@Composable
private fun sourceMeta(card: MealCard): String =
    if (card.source == MealCardSource.Photo) {
        card.modelUsed?.takeIf { it.isNotBlank() }?.let { model ->
            stringResource(R.string.stack_meta_source_photo, model)
        } ?: stringResource(R.string.today_source_photo)
    } else {
        sourceSubtitleLabel(card.source)
    }

@Composable
private fun statusHintText(card: MealCard): String =
    when (card.statusHint) {
        MealCardStatusHint.None -> if (card.state == MealCardState.Confirmed) {
            stringResource(R.string.stack_status_confirmed)
        } else {
            stringResource(R.string.today_status_draft)
        }
        MealCardStatusHint.Queued -> stringResource(R.string.outbox_state_just_queued)
        MealCardStatusHint.Uploading -> stringResource(R.string.today_status_uploading)
        MealCardStatusHint.Estimating -> stringResource(R.string.today_status_estimating)
        MealCardStatusHint.EstimatingSlow -> stringResource(R.string.outbox_state_estimating_slow)
        MealCardStatusHint.WaitingNetwork -> stringResource(R.string.today_status_waiting_network)
        MealCardStatusHint.Stuck -> stringResource(R.string.stack_status_stuck)
    }

private fun MealCard.canEditWeight(): Boolean =
    (serverId != null && primaryItemId != null) ||
        outboxItem?.let { item ->
            item.kind is OutboxKind.CreateMeal || item.draft != null
        } == true

private fun editableNumber(value: Double?): String =
    value?.let {
        if (it == it.toLong().toDouble()) it.toLong().toString() else formatGrams(it)
    }.orEmpty()

private fun stackDate(date: LocalDate): String =
    date.toJavaLocalDate().format(DateTimeFormatter.ofPattern("d MMMM", Locale("ru")))

private fun Instant.timeText(): String {
    val time = toLocalDateTime(TimeZone.currentSystemDefault()).time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}

private val CardWidth = 300.dp
