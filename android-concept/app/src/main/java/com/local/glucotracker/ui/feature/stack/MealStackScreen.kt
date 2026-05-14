package com.local.glucotracker.ui.feature.stack

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
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
import com.local.glucotracker.ui.design.primitives.GTIconButton
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.design.primitives.GTSectionLabel
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.format.formatPercent
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
    MealStackScreen(
        state = state,
        onBack = onBack,
        onPageChanged = viewModel::onPageChanged,
        onSaveTitle = viewModel::updateTitle,
        onSaveTime = viewModel::updateTime,
        onSaveWeight = viewModel::updateWeight,
        onRetry = viewModel::retryCurrent,
        modifier = modifier,
    )
}

@OptIn(ExperimentalFoundationApi::class, ExperimentalMaterial3Api::class)
@Composable
fun MealStackScreen(
    state: MealStackUiState,
    onBack: () -> Unit,
    onPageChanged: (String) -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onRetry: () -> Unit,
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
                onBack = onBack,
                onPageChanged = onPageChanged,
                onSaveTitle = onSaveTitle,
                onSaveTime = onSaveTime,
                onSaveWeight = onSaveWeight,
                onRetry = onRetry,
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun ReadyStack(
    state: MealStackUiState.Ready,
    onBack: () -> Unit,
    onPageChanged: (String) -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
    onRetry: () -> Unit,
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
        BoxWithConstraints(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalStackGestures(
                    enabled = !editSheetOpen,
                    onOpenEdit = { editSheetOpen = true },
                    onBack = onBack,
                ),
        ) {
            val horizontalPadding = ((maxWidth - CardWidth) / 2).coerceAtLeast(28.dp)
            state.cards.getOrNull(state.currentIndex + 1)?.let {
                MealCardPeek(
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .offset(x = (-146).dp, y = 8.dp),
                )
            }
            state.cards.getOrNull(state.currentIndex - 1)?.let {
                MealCardPeek(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .offset(x = 146.dp, y = 8.dp),
                )
            }
            HorizontalPager(
                state = pagerState,
                pageSize = PageSize.Fixed(CardWidth),
                contentPadding = PaddingValues(horizontal = horizontalPadding),
                pageSpacing = 12.dp,
                verticalAlignment = Alignment.Top,
                userScrollEnabled = state.cards.size > 1 && !editSheetOpen,
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(),
            ) { page ->
                val pageOffset = (
                    (pagerState.currentPage - page) + pagerState.currentPageOffsetFraction
                ).absoluteValue.coerceIn(0f, 1f)
                MealCardComposable(
                    card = state.cards[page],
                    loadPhoto = pageOffset < 0.55f,
                    onRetry = onRetry,
                    modifier = Modifier
                        .graphicsLayer {
                            alpha = 1f - pageOffset * 0.65f
                            val scale = 1f - pageOffset * 0.1f
                            scaleX = scale
                            scaleY = scale
                        }
                        .padding(top = 8.dp, bottom = 18.dp),
                )
            }
            if (editSheetOpen) {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .background(GT.colors.ink.copy(alpha = 0.16f)),
                )
            }
        }
    }

    if (editSheetOpen && currentCard != null) {
        ModalBottomSheet(
            onDismissRequest = { editSheetOpen = false },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = GT.colors.surface,
            contentColor = GT.colors.ink,
            tonalElevation = 0.dp,
        ) {
            QuickEditSheet(
                card = currentCard,
                onClose = { editSheetOpen = false },
                onSaveTitle = onSaveTitle,
                onSaveTime = onSaveTime,
                onSaveWeight = onSaveWeight,
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
            .padding(horizontal = 10.dp, vertical = 5.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(
                R.string.stack_kicker,
                stackDate(date),
                currentIndex + 1,
                total,
            ),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 9.sp),
            maxLines = 1,
        )
        Row(
            modifier = Modifier.padding(top = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            repeat(total.coerceAtMost(MaxDots)) { index ->
                val active = index == currentIndex.coerceAtMost(MaxDots - 1)
                Box(
                    modifier = Modifier
                        .size(if (active) 6.dp else 5.dp)
                        .background(
                            color = if (active) GT.colors.ink else Color.Transparent,
                            shape = CircleShape,
                        )
                        .border(
                            width = GT.space.hairline,
                            color = if (active) GT.colors.ink else GT.colors.muted,
                            shape = CircleShape,
                        ),
                )
            }
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(44.dp)
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
private fun MealCardPeek(
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(12.dp)
    val photoShape = RoundedCornerShape(8.dp)
    Column(
        modifier = modifier
            .width(CardWidth)
            .graphicsLayer {
                alpha = 0.35f
                scaleX = 0.9f
                scaleY = 0.9f
            }
            .background(GT.colors.bg, shape)
            .border(1.dp, GT.colors.ink.copy(alpha = 0.22f), shape)
            .padding(12.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(4f / 3f)
                .clip(photoShape)
                .background(GT.colors.surface)
                .border(GT.space.hairline, GT.colors.hairline2, photoShape),
        )
        Box(
            modifier = Modifier
                .padding(top = 10.dp)
                .fillMaxWidth(0.72f)
                .height(12.dp)
                .background(GT.colors.surface, RoundedCornerShape(4.dp)),
        )
        Box(
            modifier = Modifier
                .padding(top = 5.dp)
                .fillMaxWidth(0.48f)
                .height(8.dp)
                .background(GT.colors.surface, RoundedCornerShape(4.dp)),
        )
    }
}

@Composable
fun MealCardComposable(
    card: MealCard,
    loadPhoto: Boolean,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(12.dp)
    Column(
        modifier = modifier
            .width(CardWidth)
            .background(GT.colors.bg, shape)
            .border(1.dp, GT.colors.ink.copy(alpha = 0.22f), shape)
            .padding(12.dp),
    ) {
        MealCardPhoto(card = card, loadPhoto = loadPhoto, onRetry = onRetry)
        Text(
            text = card.title.orEmpty().ifBlank { fallbackTitle(card) },
            modifier = Modifier.padding(top = 10.dp),
            color = GT.colors.ink,
            style = GT.type.serifSection.copy(fontSize = 18.sp, lineHeight = 20.sp),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = cardSubtitle(card),
            modifier = Modifier.padding(top = 4.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel.copy(fontSize = 10.sp),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        MacrosBlock(
            card = card,
            modifier = Modifier.padding(top = 10.dp),
        )
        MetaBlock(
            card = card,
            modifier = Modifier.padding(top = 8.dp),
        )
        Text(
            text = stringResource(R.string.stack_gesture_edit),
            modifier = Modifier
                .padding(top = 3.dp)
                .align(Alignment.CenterHorizontally),
            color = GT.colors.muted,
            style = GT.type.kicker.copy(fontSize = 9.sp),
            maxLines = 1,
        )
    }
}

@Composable
private fun MealCardPhoto(
    card: MealCard,
    loadPhoto: Boolean,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val imageModel = if (loadPhoto) rememberApiImageModel(card.photo) else null
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
        if (card.state == MealCardState.Confirmed && card.confidence != null) {
            ConfidencePill(
                confidence = card.confidence,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(8.dp),
            )
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
        if (card.state == MealCardState.Stuck && card.outboxId != null) {
            GTOutlineButton(
                text = stringResource(R.string.outbox_retry),
                onClick = onRetry,
            )
        }
    }
}

@Composable
private fun ConfidencePill(confidence: Double, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .background(GT.colors.surface2.copy(alpha = 0.92f), RoundedCornerShape(10.dp))
            .padding(horizontal = 7.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(5.dp)
                .background(GT.colors.accent, CircleShape),
        )
        Text(
            text = stringResource(
                R.string.stack_confidence,
                formatPercent(confidence.coerceIn(0.0, 1.0) * 100.0),
            ),
            color = GT.colors.ink,
            style = GT.type.monoLabel.copy(fontSize = 9.sp),
            maxLines = 1,
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
private fun MetaBlock(card: MealCard, modifier: Modifier = Modifier) {
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
        MetaRow(
            label = stringResource(R.string.stack_meta_status),
            value = statusHintText(card),
        )
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
    onClose: () -> Unit,
    onSaveTitle: (String) -> Unit,
    onSaveTime: (String) -> Unit,
    onSaveWeight: (String) -> Unit,
) {
    var title by remember(card.id, card.title) { mutableStateOf(card.title.orEmpty()) }
    var time by remember(card.id, card.eatenAt) { mutableStateOf(card.eatenAt.timeText()) }
    var weight by remember(card.id, card.weightGrams) { mutableStateOf(editableNumber(card.weightGrams)) }
    val canEditWeight = card.canEditWeight()
    val closeDescription = stringResource(R.string.stack_edit_close)

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .fillMaxHeight(0.6f)
            .navigationBarsPadding()
            .padding(horizontal = 18.dp, vertical = 14.dp),
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
            val openThreshold = 100.dp.toPx()
            val closeThreshold = -150.dp.toPx()
            var totalDrag = 0f
            var handled = false
            detectVerticalDragGestures(
                onDragStart = {
                    totalDrag = 0f
                    handled = false
                },
                onVerticalDrag = { change, dragAmount ->
                    if (handled) return@detectVerticalDragGestures
                    totalDrag += dragAmount
                    when {
                        totalDrag > openThreshold -> {
                            handled = true
                            onBack()
                        }
                        totalDrag < closeThreshold -> {
                            handled = true
                            onOpenEdit()
                        }
                    }
                },
            )
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
private fun cardSubtitle(card: MealCard): String {
    val weight = card.weightGrams?.let { stringResource(R.string.stack_weight_value, formatGrams(it)) }
        ?: stringResource(R.string.stack_weight_value, formatGrams(100.0))
    return stringResource(
        R.string.stack_subtitle,
        sourceSubtitleLabel(card.source),
        weight,
        card.eatenAt.timeText(),
    )
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
        stringResource(R.string.stack_meta_source_photo)
    } else {
        sourceSubtitleLabel(card.source)
    }

@Composable
private fun statusHintText(card: MealCard): String =
    when (card.statusHint) {
        MealCardStatusHint.None -> stringResource(R.string.stack_status_confirmed)
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

private val CardWidth = 256.dp
private const val MaxDots = 12
