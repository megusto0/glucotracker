package com.local.glucotracker.ui.feature.capture

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.compose.BackHandler
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import java.io.File
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutLinearInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.data.repository.BrandPrefix
import com.local.glucotracker.data.repository.parsePrefix
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.ServingUnits
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.stock.MealPrepPhotoButton
import com.local.glucotracker.ui.stock.StockTag
import com.local.glucotracker.ui.image.photoContentScale
import com.local.glucotracker.ui.image.rememberApiImageModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.floor
import kotlin.math.roundToInt

internal sealed interface ComposeSuggestion {
    val id: String
    val name: String
    val kcal: Double?
    val usageCount: Int
    val imageUrl: String?
    val restaurantPrefix: String?

    /**
     * Which block of the list this belongs to: cooked batches first, then what
     * is in the fridge, then the catalogue.
     *
     * Stock is the part of the list that spoils. A yoghurt you own and a
     * yoghurt the catalogue has heard of are not equally useful answers to
     * «что я ем» — one of them is in the kitchen and going off.
     */
    val stockRank: Int

    data class ProductSuggestion(val product: Product) : ComposeSuggestion {
        override val id = "product:${product.id}"
        override val name = product.name
        override val kcal = product.kcal
        override val usageCount = product.usageCount
        override val imageUrl = product.imageUrl
        override val restaurantPrefix = product.brand?.takeIf {
            product.kind.equals("restaurant", ignoreCase = true)
        }
        override val stockRank = when (product.sourceKind) {
            "meal_prep" -> 0
            "fridge" -> 1
            else -> 2
        }
    }

    data class TemplateSuggestion(val template: Template) : ComposeSuggestion {
        override val id = "template:${template.id}"
        override val name = template.name
        override val kcal = template.defaultKcal
        override val usageCount = template.usageCount
        override val imageUrl = template.imageUrl
        override val restaurantPrefix = template.prefix.takeIf(::isRestaurantPrefix)
        override val stockRank = 2
    }

    data class RestaurantVariantsSuggestion(
        val group: RestaurantVariantGroup,
    ) : ComposeSuggestion {
        override val id = group.id
        override val name = group.name
        override val kcal = null
        override val usageCount = group.variants.sumOf { variant -> variant.usageCount }
        override val imageUrl = group.imageUrl
        override val restaurantPrefix = group.prefix
        override val stockRank = 2
    }
}

/**
 * Meal preps, then the fridge, then everything else — and inside each block the
 * order the list always had: what the query starts, then what gets eaten most,
 * then alphabetical.
 *
 * Both sheets sort through here. They carried a comparator each, which is
 * exactly how two lists of the same food end up in two different orders.
 */
internal fun List<ComposeSuggestion>.rankedFor(query: String): List<ComposeSuggestion> =
    sortedWith(
        compareBy<ComposeSuggestion> { it.stockRank }
            .thenByDescending { it.name.startsWith(query, ignoreCase = true) }
            .thenByDescending { it.usageCount }
            .thenBy { it.name },
    )

private fun isRestaurantPrefix(prefix: String): Boolean =
    prefix.lowercase() in setOf("bk", "rostics", "vit", "mc", "kfc")

@OptIn(ExperimentalMaterial3Api::class)
/**
 * The curtain's own motion. Critically damped on purpose: a spring with any
 * bounce left in it overshoots past the top edge, and on a sheet that covers
 * the whole screen the overshoot reads as a strip of scrim tearing off the
 * bottom rather than as liveliness.
 */
private val SheetSpring = spring<Float>(
    dampingRatio = Spring.DampingRatioNoBouncy,
    stiffness = Spring.StiffnessMedium,
)

/** Leaving is a decision, not a settling, so it goes at a fixed pace. */
private val SheetExit = tween<Float>(durationMillis = 170, easing = FastOutLinearInEasing)

/** A flick this fast closes the sheet wherever it happens to be. */
private const val SheetFlingToClose = 1400f

/** Below a third of the way down, letting go puts it back. */
private const val SheetCloseFraction = 0.33f

@Composable
fun ManualEntrySearchSheet(
    onDismiss: () -> Unit,
    onOutboxQueued: (String) -> Unit,
    viewModel: CaptureViewModel = hiltViewModel(),
) {
    val openCount by viewModel.composeSheetOpenCount.collectAsStateWithLifecycle(initialValue = 0)
    var dismissRequested by remember { mutableStateOf(false) }

    fun requestDismiss() {
        dismissRequested = true
    }

    LaunchedEffect(Unit) {
        viewModel.onComposeSheetOpened()
    }

    BackHandler(onBack = ::requestDismiss)
    Dialog(
        onDismissRequest = ::requestDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val fullHeight = with(LocalDensity.current) { maxHeight.toPx() }
            // How far down the sheet sits: full height is off the bottom edge,
            // zero is open. One value drives the slide, the drag and the scrim,
            // so a half-dragged sheet cannot disagree with the dark behind it.
            val offsetY = remember { Animatable(fullHeight) }
            val scope = rememberCoroutineScope()

            LaunchedEffect(Unit) {
                offsetY.animateTo(0f, SheetSpring)
            }
            LaunchedEffect(dismissRequested) {
                if (dismissRequested) {
                    offsetY.animateTo(fullHeight, SheetExit)
                    onDismiss()
                }
            }

            val openFraction = (1f - offsetY.value / fullHeight).coerceIn(0f, 1f)
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(GT.colors.ink.copy(alpha = 0.55f * openFraction)),
            )
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    // Clamped, so a stray negative never lifts the sheet off
                    // the top and shows daylight under it.
                    .offset { IntOffset(0, offsetY.value.coerceAtLeast(0f).roundToInt()) }
                    .clip(RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp))
                    .background(GT.colors.bg),
            ) {
                JournalDragHandle(
                    modifier = Modifier.draggable(
                        orientation = Orientation.Vertical,
                        state = rememberDraggableState { delta ->
                            scope.launch {
                                // Downwards only. The sheet is already at the
                                // ceiling; dragging up has nothing to reveal.
                                offsetY.snapTo((offsetY.value + delta).coerceAtLeast(0f))
                            }
                        },
                        onDragStopped = { velocity ->
                            val flung = velocity > SheetFlingToClose
                            val pulledFarEnough = offsetY.value > fullHeight * SheetCloseFraction
                            if (flung || pulledFarEnough) {
                                requestDismiss()
                            } else {
                                offsetY.animateTo(0f, SheetSpring)
                            }
                        },
                    ),
                )
                ManualEntrySearchSheetContent(
                    openCount = openCount,
                    onDismiss = ::requestDismiss,
                    onSubmitText = { text ->
                        viewModel.enqueueTextMeal(text) { outboxId ->
                            requestDismiss()
                            onOutboxQueued(outboxId)
                        }
                    },
                    onSubmitProduct = { product, weightGrams, servingText, containers ->
                        viewModel.enqueueProductMeal(
                            product,
                            weightGrams,
                            servingText,
                            mealprepContainers = containers,
                        ) { outboxId ->
                            requestDismiss()
                            onOutboxQueued(outboxId)
                        }
                    },
                    onSubmitTemplate = { template ->
                        viewModel.enqueueFromTemplate(template, template.defaultGrams) { outboxId ->
                            requestDismiss()
                            onOutboxQueued(outboxId)
                        }
                    },
                    searchProducts = viewModel::searchProducts,
                    searchTemplates = viewModel::searchTemplates,
                    openStockProduct = viewModel::openStockProduct,
                    onMealPrepPhoto = viewModel::uploadMealPrepPhoto,
                    modifier = Modifier
                        .fillMaxWidth()
                        .fillMaxHeight()
                        .imePadding(),
                )
            }
        }
    }
}

@Composable
fun ManualEntrySearchSheetContent(
    openCount: Int,
    onDismiss: () -> Unit,
    onSubmitText: (String) -> Unit,
    onSubmitProduct: (Product, Double?, String?, Int?) -> Unit,
    onSubmitTemplate: (Template) -> Unit,
    searchProducts: (String, BrandPrefix?, (List<Product>) -> Unit) -> Unit,
    searchTemplates: (String, (List<Template>) -> Unit) -> Unit,
    modifier: Modifier = Modifier,
    openStockProduct: ((Product, (Product) -> Unit) -> Unit)? = null,
    onServingUnitChosen: ((productId: String, unit: String) -> Unit)? = null,
    onMealPrepPhoto: ((productId: String, localPath: String, onResult: (String?) -> Unit) -> Unit)? = null,
    initialText: String = "",
    initialProducts: List<Product> = emptyList(),
    initialTemplates: List<Template> = emptyList(),
) {
    var text by remember { mutableStateOf(initialText) }
    var products by remember { mutableStateOf(initialProducts) }
    var templates by remember { mutableStateOf(initialTemplates) }
    var selectedRestaurantGroup by remember { mutableStateOf<RestaurantVariantGroup?>(null) }
    var selectedProductForPortion by remember { mutableStateOf<Product?>(null) }
    var restoreSearchFocus by remember { mutableStateOf(false) }
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current
    val query = text.trim()

    LaunchedEffect(text) {
        delay(50)
        val currentText = text
        val currentQuery = query
        searchProducts(currentQuery, null) { found ->
            if (currentText == text) products = found
        }
        searchTemplates(currentQuery) { found ->
            if (currentText == text) templates = found
        }
    }

    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
        keyboardController?.show()
    }

    LaunchedEffect(restoreSearchFocus) {
        if (restoreSearchFocus) {
            focusRequester.requestFocus()
            keyboardController?.show()
            restoreSearchFocus = false
        }
    }

    val suggestions = remember(products, templates, query) {
        (products.map { ComposeSuggestion.ProductSuggestion(it) } +
            restaurantTemplateChoices(templates).map { choice ->
                when (choice) {
                    is RestaurantTemplateChoice.Single ->
                        ComposeSuggestion.TemplateSuggestion(choice.template)
                    is RestaurantTemplateChoice.Variants ->
                        ComposeSuggestion.RestaurantVariantsSuggestion(choice.group)
                }
            })
            .rankedFor(query)
    }
    val canSubmitFreeform = query.isNotBlank() &&
        suggestions.none { it.name.equals(query, ignoreCase = true) }

    selectedRestaurantGroup?.let { group ->
        RestaurantVariantPicker(
            group = group,
            onBack = {
                selectedRestaurantGroup = null
                restoreSearchFocus = true
            },
            onCancel = onDismiss,
            onSubmit = onSubmitTemplate,
            modifier = modifier,
        )
        return
    }

    selectedProductForPortion?.let { prod ->
        ProductPortionPicker(
            product = prod,
            onBack = {
                selectedProductForPortion = null
                restoreSearchFocus = true
            },
            onCancel = onDismiss,
            onSubmit = { product, weightGrams, servingText, containers ->
                onSubmitProduct(product, weightGrams, servingText, containers)
            },
            modifier = modifier,
            onPhotoTaken = onMealPrepPhoto,
            onServingUnitChosen = onServingUnitChosen,
        )
        return
    }

    Column(
        modifier = modifier
            .testTag("manual-entry-search-sheet")
            .background(GT.colors.bg),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.manual_entry_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
                maxLines = 1,
            )
            Text(
                text = stringResource(R.string.manual_entry_cancel),
                modifier = Modifier.clickable(onClick = onDismiss),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
                maxLines = 1,
            )
        }
        ManualSearchInput(
            value = text,
            onValueChange = { text = it },
            onSubmit = {
                if (query.isNotBlank()) onSubmitText(query)
            },
            focusRequester = focusRequester,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
        )
        Text(
            text = manualListHeader(query = query, count = suggestions.size),
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 6.dp),
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
        )
        val suggestionListState = rememberLazyListState()
            // A new query is a new list, and it has to start at the top.
            // Compose keeps the scroll offset across changes, and with stable
            // keys it follows the row you were looking at — so typing one more
            // letter left you halfway down results whose best match was the
            // first one.
        LaunchedEffect(query) { suggestionListState.scrollToItem(0) }
        LazyColumn(
            state = suggestionListState,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .background(GT.colors.surface),
        ) {
            if (suggestions.isEmpty() && query.isBlank()) {
                item("empty-db") {
                    ManualEmptyRow(text = stringResource(R.string.manual_entry_empty_database))
                }
            }
            items(suggestions, key = { it.id }) { item ->
                ManualSuggestionRow(
                    item = item,
                    query = query,
                    onClick = {
                        when (item) {
                            is ComposeSuggestion.ProductSuggestion -> {
                                keyboardController?.hide()
                                if (item.product.isStock && openStockProduct != null) {
                                    openStockProduct(item.product) { selectedProductForPortion = it }
                                } else {
                                    selectedProductForPortion = item.product
                                }
                            }
                            is ComposeSuggestion.TemplateSuggestion -> onSubmitTemplate(item.template)
                            is ComposeSuggestion.RestaurantVariantsSuggestion -> {
                                keyboardController?.hide()
                                selectedRestaurantGroup = item.group
                            }
                        }
                    },
                )
            }
            if (canSubmitFreeform) {
                item("freeform") {
                    ManualNoMatchRow(
                        query = query,
                        onClick = { onSubmitText(query) },
                    )
                }
            }
        }
        if (openCount < 3) {
            Text(
                text = stringResource(R.string.compose_sheet_prefix_hint),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp, vertical = 8.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun ManualSearchInput(
    value: String,
    onValueChange: (String) -> Unit,
    onSubmit: () -> Unit,
    focusRequester: FocusRequester,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .height(46.dp)
            .background(GT.colors.surface2, RoundedCornerShape(14.dp))
            .border(1.5.dp, GT.colors.ink, RoundedCornerShape(14.dp))
            .padding(horizontal = 14.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (value.isEmpty()) {
            Text(
                text = stringResource(R.string.manual_entry_search_placeholder),
                color = GT.colors.muted,
                style = GT.type.sansBody,
                maxLines = 1,
            )
        }
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier
                .fillMaxWidth()
                .focusRequester(focusRequester),
            textStyle = GT.type.sansBody.copy(color = GT.colors.ink),
            cursorBrush = SolidColor(GT.colors.ink),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { onSubmit() }),
            singleLine = true,
        )
    }
}

@Composable
private fun ManualSuggestionRow(
    item: ComposeSuggestion,
    query: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SuggestionThumb(item = item)
        Spacer(Modifier.width(11.dp))
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                HighlightedName(
                    name = item.name,
                    queryPrefix = query,
                    modifier = Modifier.weight(1f, fill = false),
                )
                // Same mark as База. Search is where a fridge item is usually
                // met first, and there it looked like any other product.
                (item as? ComposeSuggestion.ProductSuggestion)?.product?.let { product ->
                    if (product.isStock) {
                        Spacer(Modifier.width(6.dp))
                        StockTag(product)
                    }
                }
            }
            Text(
                text = item.restaurantPrefix?.let { restaurantPrefix ->
                    restaurantMeta(item, restaurantPrefix)
                } ?: (item as? ComposeSuggestion.ProductSuggestion)?.product?.subtitle?.takeIf { it.isNotBlank() }
                  ?: stringResource(R.string.manual_entry_suggestion_meta, item.usageCount),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        item.kcal?.let { kcal ->
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = formatKcal(kcal),
                    color = GT.colors.ink,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
                Text(
                    text = stringResource(R.string.manual_entry_kcal_unit),
                    color = GT.colors.muted,
                    style = GT.type.kicker,
                    maxLines = 1,
                )
            }
        }
    }
    GTHairlineDivider()
}

@Composable
private fun SuggestionThumb(item: ComposeSuggestion) {
    val imageModel = rememberApiImageModel(item.imageUrl)
    Box(
        modifier = Modifier
            .size(32.dp)
            .background(GT.colors.bg, RoundedCornerShape(7.dp))
            .border(GT.space.hairline, GT.colors.hairline2, RoundedCornerShape(7.dp)),
        contentAlignment = Alignment.Center,
    ) {
        if (imageModel != null) {
            AsyncImage(
                model = imageModel,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Text(
                text = item.name.firstOrNull()?.uppercaseChar()?.toString().orEmpty(),
                color = GT.colors.muted,
                style = GT.type.kicker,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun HighlightedName(
    name: String,
    queryPrefix: String,
    modifier: Modifier = Modifier,
) {
    if (queryPrefix.isBlank() || !name.startsWith(queryPrefix, ignoreCase = true)) {
        Text(
            text = name,
            modifier = modifier,
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        return
    }
    val safeLength = queryPrefix.length.coerceAtMost(name.length)
    Text(
        text = buildAnnotatedString {
            pushStyle(SpanStyle(background = GT.colors.warn.copy(alpha = 0.16f)))
            append(name.substring(0, safeLength))
            pop()
            append(name.substring(safeLength))
        },
        modifier = modifier,
        color = GT.colors.ink,
        style = GT.type.sansLabel,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun ManualNoMatchRow(query: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.manual_entry_no_match, query),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
    GTHairlineDivider()
}

@Composable
private fun ManualEmptyRow(text: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp)
            .padding(horizontal = 16.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(
            text = text,
            color = GT.colors.muted,
            style = GT.type.sansLabel,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun manualListHeader(query: String, count: Int): String =
    when {
        query.isBlank() -> stringResource(R.string.manual_entry_header_empty)
        count > 0 -> stringResource(R.string.manual_entry_header_results, count)
        else -> stringResource(R.string.manual_entry_header_no_results)
    }

@Composable
private fun JournalDragHandle(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            // The bar is 4 dp tall; the strip around it is what a thumb
            // actually lands on, so the grab area is padded well past it.
            .padding(top = 14.dp, bottom = 12.dp),
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GTComposeSheet(
    onDismiss: () -> Unit,
    onCameraClick: () -> Unit,
    onOutboxQueued: (String) -> Unit,
    viewModel: CaptureViewModel = hiltViewModel(),
) {
    val galleryLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        uri?.let {
            viewModel.enqueueGalleryPhoto(it) { outboxId ->
                onDismiss()
                onOutboxQueued(outboxId)
            }
        }
    }
    val openCount by viewModel.composeSheetOpenCount.collectAsStateWithLifecycle(initialValue = 0)

    LaunchedEffect(Unit) {
        viewModel.onComposeSheetOpened()
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = GT.colors.bg,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
    ) {
        GTComposeSheetContent(
            openCount = openCount,
            onCameraClick = {
                onDismiss()
                onCameraClick()
            },
            onGalleryClick = {
                galleryLauncher.launch(
                    PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                )
            },
            onSubmitText = { text ->
                viewModel.enqueueTextMeal(text) { outboxId ->
                    onDismiss()
                    onOutboxQueued(outboxId)
                }
            },
            onSubmitProduct = { product ->
                viewModel.enqueueProductMeal(product, product.defaultGrams) { outboxId ->
                    onDismiss()
                    onOutboxQueued(outboxId)
                }
            },
            onSubmitTemplate = { template ->
                viewModel.enqueueFromTemplate(template, template.defaultGrams) { outboxId ->
                    onDismiss()
                    onOutboxQueued(outboxId)
                }
            },
            onDismiss = onDismiss,
            searchProducts = viewModel::searchProducts,
            searchTemplates = viewModel::searchTemplates,
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.8f)
                .navigationBarsPadding()
                .imePadding(),
        )
    }
}

@Composable
fun GTComposeSheetContent(
    openCount: Int,
    onCameraClick: () -> Unit,
    onGalleryClick: () -> Unit,
    onSubmitText: (String) -> Unit,
    onSubmitProduct: (Product) -> Unit,
    onSubmitTemplate: (Template) -> Unit,
    searchProducts: (String, BrandPrefix?, (List<Product>) -> Unit) -> Unit,
    searchTemplates: (String, (List<Template>) -> Unit) -> Unit,
    onDismiss: () -> Unit = {},
    modifier: Modifier = Modifier,
    initialText: String = "",
    initialProducts: List<Product> = emptyList(),
    initialTemplates: List<Template> = emptyList(),
) {
    var text by remember { mutableStateOf(initialText) }
    var products by remember { mutableStateOf(initialProducts) }
    var templates by remember { mutableStateOf(initialTemplates) }
    var selectedRestaurantGroup by remember { mutableStateOf<RestaurantVariantGroup?>(null) }
    var showHint by remember(openCount) { mutableStateOf(openCount < 3) }
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current
    val (prefix, parsedQuery) = remember(text) { parsePrefix(text) }
    val query = parsedQuery.trim()
    val cameraLabel = stringResource(R.string.compose_sheet_camera)
    val galleryLabel = stringResource(R.string.compose_sheet_gallery)
    val placeholder = stringResource(R.string.compose_sheet_placeholder)
    val submitLabel = stringResource(R.string.compose_sheet_submit)
    val hintLabel = stringResource(R.string.compose_sheet_hint)
    val prefixHint = stringResource(R.string.compose_sheet_prefix_hint)

    LaunchedEffect(text) {
        delay(50)
        val currentText = text
        val currentPrefix = prefix
        val currentQuery = query
        if (currentPrefix != BrandPrefix.Template) {
            searchProducts(currentQuery, currentPrefix) { found ->
                if (currentText == text) products = found
            }
        } else {
            products = emptyList()
        }
        if (currentPrefix == null || currentPrefix == BrandPrefix.Template) {
            searchTemplates(currentQuery) { found ->
                if (currentText == text) templates = found
            }
        } else {
            templates = emptyList()
        }
    }

    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
        keyboardController?.show()
    }

    val suggestions = remember(products, templates, query) {
        (restaurantTemplateChoices(templates).map { choice ->
            when (choice) {
                is RestaurantTemplateChoice.Single ->
                    ComposeSuggestion.TemplateSuggestion(choice.template)
                is RestaurantTemplateChoice.Variants ->
                    ComposeSuggestion.RestaurantVariantsSuggestion(choice.group)
            }
        } +
            products.map { ComposeSuggestion.ProductSuggestion(it) })
            .rankedFor(query)
    }
    val hasExactMatch = suggestions.any { it.name.equals(query, ignoreCase = true) }
    val canSubmitFreeform = query.isNotBlank() && !hasExactMatch

    selectedRestaurantGroup?.let { group ->
        RestaurantVariantPicker(
            group = group,
            onBack = {
                selectedRestaurantGroup = null
                focusRequester.requestFocus()
                keyboardController?.show()
            },
            onCancel = onDismiss,
            onSubmit = onSubmitTemplate,
            modifier = modifier,
        )
        return
    }

    Column(
        modifier = modifier
            .testTag("gt-compose-sheet")
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SheetIconButton(
                contentDescription = cameraLabel,
                onClick = onCameraClick,
            ) { CaptureGlyph(CaptureGlyphKind.Camera) }
            Spacer(Modifier.width(8.dp))
            SheetIconButton(
                contentDescription = galleryLabel,
                onClick = onGalleryClick,
            ) { CaptureGlyph(CaptureGlyphKind.Gallery) }
            Spacer(Modifier.width(12.dp))
            Box(modifier = Modifier.weight(1f)) {
                if (text.isEmpty()) {
                    Text(
                        text = placeholder,
                        color = GT.colors.muted,
                        style = GT.type.sansBody,
                        maxLines = 1,
                    )
                }
                BasicTextField(
                    value = text,
                    onValueChange = { text = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(focusRequester)
                        .testTag("gt-compose-input"),
                    textStyle = GT.type.sansBody.copy(color = GT.colors.ink),
                    cursorBrush = SolidColor(GT.colors.ink),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(
                        onSend = {
                            if (query.isNotBlank()) onSubmitText(query)
                        },
                    ),
                    singleLine = true,
                )
            }
            if (query.isNotBlank()) {
                Spacer(Modifier.width(8.dp))
                SheetIconButton(
                    contentDescription = submitLabel,
                    onClick = { onSubmitText(query) },
                ) {
                    Text("в†‘", color = GT.colors.ink, style = GT.type.sansLabel)
                }
            } else if (openCount >= 3) {
                Spacer(Modifier.width(8.dp))
                SheetIconButton(
                    contentDescription = hintLabel,
                    onClick = { showHint = !showHint },
                ) {
                    Text("?", color = GT.colors.ink2, style = GT.type.sansLabel)
                }
            }
        }
        GTHairlineDivider()
        val suggestionListState = rememberLazyListState()
        LaunchedEffect(query) { suggestionListState.scrollToItem(0) }
        LazyColumn(state = suggestionListState, modifier = Modifier.weight(1f)) {
            items(suggestions, key = { it.id }) { item ->
                ComposeSuggestionRow(
                    item = item,
                    onClick = {
                        when (item) {
                            is ComposeSuggestion.ProductSuggestion -> onSubmitProduct(item.product)
                            is ComposeSuggestion.TemplateSuggestion -> onSubmitTemplate(item.template)
                            is ComposeSuggestion.RestaurantVariantsSuggestion -> {
                                keyboardController?.hide()
                                selectedRestaurantGroup = item.group
                            }
                        }
                    },
                )
            }
            if (canSubmitFreeform) {
                item("freeform") {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp)
                            .clickable { onSubmitText(query) }
                            .padding(horizontal = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = stringResource(R.string.compose_sheet_freeform, query),
                            color = GT.colors.ink,
                            style = GT.type.sansLabel,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    GTHairlineDivider()
                }
            }
        }
        if (showHint) {
            Text(
                text = prefixHint,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(24.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun ComposeSuggestionRow(
    item: ComposeSuggestion,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(48.dp)
            .clickable(onClick = onClick)
            .padding(horizontal = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SuggestionThumb(item = item)
        Spacer(Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = item.name,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            item.restaurantPrefix?.let { restaurantPrefix ->
                Text(
                    text = restaurantMeta(item, restaurantPrefix),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        item.kcal?.let { kcal ->
            Text(
                text = stringResource(R.string.compose_sheet_kcal, formatKcal(kcal)),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
            Spacer(Modifier.width(10.dp))
        }
        if (item.usageCount > 0) {
            Box(
                modifier = Modifier
                    .background(GT.colors.surface, GT.shapes.tag)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.tag)
                    .padding(horizontal = 7.dp, vertical = 2.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = stringResource(R.string.compose_sheet_usage_count, item.usageCount),
                    color = GT.colors.muted,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
        }
    }
    GTHairlineDivider()
}

@Composable
private fun RestaurantVariantPicker(
    group: RestaurantVariantGroup,
    onBack: () -> Unit,
    onCancel: () -> Unit,
    onSubmit: (Template) -> Unit,
    modifier: Modifier = Modifier,
) {
    val initialVariant = remember(group.id) {
        group.variants.maxWithOrNull(
            compareBy<Template> { it.usageCount }
                .thenByDescending { restaurantQuantity(it.name) ?: Int.MAX_VALUE },
        ) ?: group.variants.first()
    }
    var selectedVariant by remember(group.id) { mutableStateOf(initialVariant) }
    val quantities = group.quantityOptions
    val selectedQuantityIndex = quantities.indexOf(restaurantQuantity(selectedVariant.name)).coerceAtLeast(0)
    val imageModel = rememberApiImageModel(selectedVariant.imageUrl ?: group.imageUrl)

    Column(
        modifier = modifier
            .testTag("restaurant-variant-picker")
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.restaurant_variant_back),
                modifier = Modifier
                    .heightIn(min = 44.dp)
                    .clickable(onClick = onBack)
                    .padding(vertical = 14.dp),
                color = GT.colors.ink2,
                style = GT.type.sansLabel,
            )
            Text(
                text = stringResource(R.string.manual_entry_cancel),
                modifier = Modifier
                    .heightIn(min = 44.dp)
                    .clickable(onClick = onCancel)
                    .padding(vertical = 14.dp),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }
        GTHairlineDivider()
        Spacer(Modifier.height(12.dp))
        if (imageModel != null) {
            AsyncImage(
                model = imageModel,
                contentDescription = stringResource(
                    R.string.restaurant_variant_image_a11y,
                    selectedVariant.name,
                ),
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(138.dp)
                    .background(GT.colors.surface, GT.shapes.card)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card),
            )
            Spacer(Modifier.height(12.dp))
        }
        Text(
            text = group.name,
            color = GT.colors.ink,
            style = GT.type.serifSection,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = restaurantName(group.prefix),
            modifier = Modifier.padding(top = 3.dp),
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
        )
        Spacer(Modifier.height(14.dp))

        if (group.hasQuantitySlider) {
            Text(
                text = stringResource(R.string.restaurant_variant_choose_quantity),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            Text(
                text = stringResource(
                    R.string.restaurant_variant_quantity_value,
                    quantities[selectedQuantityIndex],
                ),
                modifier = Modifier.padding(top = 4.dp),
                color = GT.colors.ink,
                style = GT.type.monoNumber,
            )
            Slider(
                value = selectedQuantityIndex.toFloat(),
                onValueChange = { value ->
                    val quantity = quantities[value.roundToInt().coerceIn(quantities.indices)]
                    variantForQuantity(group, quantity)?.let { selectedVariant = it }
                },
                valueRange = 0f..quantities.lastIndex.toFloat(),
                steps = (quantities.size - 2).coerceAtLeast(0),
                colors = SliderDefaults.colors(
                    thumbColor = GT.colors.ink,
                    activeTrackColor = GT.colors.ink,
                    inactiveTrackColor = GT.colors.hairline2,
                ),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                quantities.forEach { quantity ->
                    Text(
                        text = quantity.toString(),
                        color = if (quantity == quantities[selectedQuantityIndex]) GT.colors.ink else GT.colors.muted,
                        style = GT.type.monoLabel,
                    )
                }
            }
        } else {
            Text(
                text = stringResource(R.string.restaurant_variant_choose_kind),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 210.dp)
                    .padding(top = 6.dp),
            ) {
                items(group.variants, key = { variant -> variant.id }) { variant ->
                    val selected = variant.id == selectedVariant.id
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .background(if (selected) GT.colors.surface else GT.colors.bg, GT.shapes.card)
                            .border(
                                GT.space.hairline,
                                if (selected) GT.colors.ink else GT.colors.hairline2,
                                GT.shapes.card,
                            )
                            .clickable { selectedVariant = variant }
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = variant.name,
                            modifier = Modifier.weight(1f),
                            color = GT.colors.ink,
                            style = GT.type.sansLabel,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (selected) {
                            Text(
                                text = stringResource(R.string.restaurant_variant_selected),
                                modifier = Modifier.padding(start = 8.dp),
                                color = GT.colors.ink2,
                                style = GT.type.monoLabel,
                            )
                        }
                    }
                    Spacer(Modifier.height(6.dp))
                }
            }
        }

        Text(
            text = stringResource(
                R.string.restaurant_variant_macros,
                selectedVariant.defaultKcal?.let(::formatKcal) ?: "—",
                selectedVariant.defaultProteinG?.let(::formatGrams) ?: "—",
                selectedVariant.defaultFatG?.let(::formatGrams) ?: "—",
                selectedVariant.defaultCarbsG?.let(::formatGrams) ?: "—",
            ),
            modifier = Modifier.padding(top = 14.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
            maxLines = 2,
        )
        GTOutlineButton(
            text = stringResource(R.string.restaurant_variant_add),
            onClick = { onSubmit(selectedVariant) },
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 14.dp, bottom = 18.dp),
        )
    }
}

@Composable
private fun restaurantMeta(item: ComposeSuggestion, prefix: String): String {
    val restaurant = restaurantName(prefix)
    return if (item is ComposeSuggestion.RestaurantVariantsSuggestion) {
        stringResource(R.string.restaurant_variants_count, restaurant, item.group.variants.size)
    } else {
        restaurant
    }
}

@Composable
private fun restaurantName(prefix: String): String = when (prefix.lowercase()) {
    "bk" -> stringResource(R.string.restaurant_burger_king)
    "rostics", "kfc" -> stringResource(R.string.restaurant_rostics)
    "vit", "mc" -> stringResource(R.string.restaurant_vkusno_i_tochka)
    else -> prefix.uppercase()
}

@Composable
private fun SheetIconButton(
    contentDescription: String,
    onClick: () -> Unit,
    content: @Composable () -> Unit,
) {
    IconButton(
        onClick = onClick,
        modifier = Modifier
            .size(32.dp)
            .background(GT.colors.surface, GT.shapes.iconButton)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.iconButton)
            .semantics { this.contentDescription = contentDescription },
    ) {
        Box(contentAlignment = Alignment.Center) {
            content()
        }
    }
}

private enum class CaptureGlyphKind {
    Camera,
    Gallery,
}

@Composable
private fun CaptureGlyph(kind: CaptureGlyphKind) {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(18.dp)) {
        val stroke = Stroke(width = 1.4.dp.toPx(), cap = StrokeCap.Round)
        when (kind) {
            CaptureGlyphKind.Camera -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(2.dp.toPx(), 5.dp.toPx()),
                    size = Size(14.dp.toPx(), 10.dp.toPx()),
                    cornerRadius = CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                    style = stroke,
                )
                drawCircle(
                    color = color,
                    radius = 2.8.dp.toPx(),
                    center = Offset(9.dp.toPx(), 10.dp.toPx()),
                    style = stroke,
                )
                drawLine(
                    color = color,
                    start = Offset(6.dp.toPx(), 5.dp.toPx()),
                    end = Offset(7.dp.toPx(), 3.dp.toPx()),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
                drawLine(
                    color = color,
                    start = Offset(7.dp.toPx(), 3.dp.toPx()),
                    end = Offset(11.dp.toPx(), 3.dp.toPx()),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
            }
            CaptureGlyphKind.Gallery -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(3.dp.toPx(), 3.dp.toPx()),
                    size = Size(12.dp.toPx(), 12.dp.toPx()),
                    cornerRadius = CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                    style = stroke,
                )
                drawLine(
                    color = color,
                    start = Offset(5.dp.toPx(), 13.dp.toPx()),
                    end = Offset(8.dp.toPx(), 10.dp.toPx()),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
                drawLine(
                    color = color,
                    start = Offset(8.dp.toPx(), 10.dp.toPx()),
                    end = Offset(11.dp.toPx(), 12.dp.toPx()),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
                drawCircle(color = color, radius = 1.1.dp.toPx(), center = Offset(7.dp.toPx(), 7.dp.toPx()))
            }
        }
    }
}

/**
 * The one question the app cannot answer for itself.
 *
 * Asked once per product and kept in the fridge, because the answer belongs to
 * the food: a tub of ice cream is eaten by the spoonful wherever it is shown.
 * There is no «later» here on purpose — a default would be a guess wearing the
 * clothes of an answer, and nobody would ever be asked to correct it.
 */
@Composable
private fun ServingUnitQuestion(
    pieceGrams: Double?,
    onAnswer: (String) -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = "Как это едят?",
            color = GT.colors.ink,
            style = GT.type.sansLabel,
        )
        Text(
            text = "Спросим один раз — дальше запомним",
            modifier = Modifier.padding(top = 2.dp),
            color = GT.colors.muted,
            style = GT.type.kicker,
        )
        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // The piece weight is the whole point of the choice: «целиком» is
            // only a sensible answer when you can see what one weighs.
            ServingUnitChoice(
                title = "Целиком",
                detail = pieceGrams?.let { "${it.roundToInt()} г за штуку" } ?: "по штукам",
                modifier = Modifier.weight(1f),
                onClick = { onAnswer(ServingUnits.Pieces) },
            )
            ServingUnitChoice(
                title = "По весу",
                detail = "граммами",
                modifier = Modifier.weight(1f),
                onClick = { onAnswer(ServingUnits.Grams) },
            )
        }
    }
}

@Composable
private fun ServingUnitChoice(
    title: String,
    detail: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Column(
        modifier = modifier
            .background(GT.colors.surface, RoundedCornerShape(8.dp))
            .border(GT.space.hairline, GT.colors.hairline2, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
    ) {
        Text(text = title, color = GT.colors.ink, style = GT.type.monoLabel)
        Text(
            text = detail,
            modifier = Modifier.padding(top = 2.dp),
            color = GT.colors.muted,
            style = GT.type.kicker,
        )
    }
}

/**
 * «1 контейнер», «2 контейнера», «5 контейнеров» — a count with its noun.
 *
 * «шт» is left alone: it is an abbreviation and does not decline, which is
 * exactly why the picker could get away with never thinking about this before.
 */
internal fun countLabel(count: Int, containers: Boolean): String {
    if (!containers) return "$count шт"
    val teens = count % 100 in 11..14
    val ones = count % 10
    val noun = when {
        teens -> "контейнеров"
        ones == 1 -> "контейнер"
        ones in 2..4 -> "контейнера"
        else -> "контейнеров"
    }
    return "$count $noun"
}

@Composable
private fun ProductPortionPicker(
    product: Product,
    onBack: () -> Unit,
    onCancel: () -> Unit,
    onSubmit: (Product, Double?, String?, Int?) -> Unit,
    modifier: Modifier = Modifier,
    // Null where nothing can upload. A meal prep is cooked once and looks the
    // same in every container, so one photograph at the counter serves all of
    // them — and until now there was no way to take it from the phone at all.
    onPhotoTaken: ((productId: String, localPath: String, onResult: (String?) -> Unit) -> Unit)? = null,
    // Where the answer goes. Null in previews and in sheets with no fridge
    // behind them; the choice still applies on screen, it just is not kept.
    onServingUnitChosen: ((productId: String, unit: String) -> Unit)? = null,
) {
    // All four of these used to be read out of the serving sentence with
    // regular expressions — «🍱 Милпреп · 300 г (GT:C:…)», «❄️ Холодильник ·
    // 4 шт в наличии». That made the wording load-bearing: reword the sentence
    // and a piece item silently became a gram item, and «шт» anywhere in a
    // product's own name turned it into one. The server sends the facts now.
    val isMealPrep = product.sourceKind == "meal_prep"
    val isFridge = product.sourceKind == "fridge"
    // Pieces whenever the fridge knows what one weighs — not only when the lot
    // happens to be counted in pieces. A 0,9 kg bag of apples is still eaten
    // one apple at a time, and «50 г / 100 г» is not how anyone thinks about it.
    val pieceGrams = product.pieceWeightG?.takeIf { it > 0 }
    // What the fridge was told, or what was just chosen on this screen. Held
    // locally too so the sheet answers the moment it is tapped, without
    // waiting for the round trip that stores it.
    var chosenUnit by remember(product.id) { mutableStateOf(product.servingUnit) }
    val isPcsItem = when {
        // A batch is portioned into containers once and eaten a container at
        // a time. Consuming one empties it whole whatever weight is recorded
        // against it, so grams were never a choice the fridge could honour —
        // «две трети контейнера» left stock on the shelf that nobody had.
        isMealPrep -> true
        // The fridge holds the answer for its own stock. Nothing here could
        // work it out: an apple and a jar of sweetener both weigh 180 g
        // apiece, and guessing offered «1 шт» for a 520 g tub of ice cream.
        product.isStock && chosenUnit != null -> chosenUnit == ServingUnits.Pieces
        product.isStock -> product.isPieces || pieceGrams != null
        // Catalogue products carry no stock, and rows cached before the fields
        // existed carry no sourceKind. Both keep the old guess.
        else -> product.name.contains("шт", ignoreCase = true)
    }

    val maxPcs: Double = remember(
        product.stockRemaining,
        pieceGrams,
        product.isPieces,
        product.containersLeft,
        isMealPrep,
    ) {
        if (isMealPrep) return@remember product.containerCount.toDouble()
        val remaining = product.stockRemaining?.takeIf { it > 0 } ?: return@remember 3.0
        when {
            // Whole pieces only, and never more than are there. A slider that
            // ran to 2,7 offered a portion no shelf could supply.
            product.isPieces -> floor(remaining).coerceAtLeast(1.0)
            // A weighed lot: how many whole pieces are left in it.
            pieceGrams != null -> floor(remaining / pieceGrams).coerceAtLeast(1.0)
            else -> 3.0
        }
    }
    // Grams still on the shelf, whichever way the lot is counted. A pack held
    // as «шт» reports 0,244 of itself left, which is 220 g of a 900 g bottle —
    // and the slider was reading the bottle instead of what is in it.
    val remainingGrams: Double? = remember(
        product.stockRemaining,
        product.isPieces,
        pieceGrams,
        product.isStock,
    ) {
        when {
            !product.isStock -> null
            product.isPieces -> product.stockRemaining?.let { left ->
                pieceGrams?.let { one -> left * one }
            }
            // Already grams: the server normalises kilograms before sending.
            else -> product.stockRemaining
        }
    }

    val maxGrams: Double = remember(
        product.stockRemaining,
        product.defaultGrams,
        product.stockUnit,
        isMealPrep,
        product.isPieces,
        remainingGrams,
    ) {
        when {
            // A batch is weighed in grams. stockRemaining used to be the number
            // of leftover containers, which made the gram slider's ceiling 3.
            isMealPrep -> {
                val remaining = product.stockRemaining
                val unit = product.stockUnit.orEmpty()
                val fromSubtitle = Regex("""(\d+(?:[.,]\d+)?)\s*г""")
                    .find(product.subtitle.orEmpty())
                    ?.groupValues
                    ?.get(1)
                    ?.replace(",", ".")
                    ?.toDoubleOrNull()
                val candidates = listOfNotNull(
                    remaining?.takeIf { it > 20.0 && unit != "контейнер" },
                    product.defaultGrams?.takeIf { it > 20.0 },
                    fromSubtitle?.takeIf { it > 20.0 },
                )
                candidates.maxOrNull() ?: remaining ?: product.defaultGrams ?: 300.0
            }
            // Never more than is left. A pack counted in pieces used to fall
            // through to defaultGrams — the weight of a full one — so a bottle
            // with a fifth of it remaining offered «Вся (900 г)».
            product.isStock -> remainingGrams ?: product.defaultGrams ?: 300.0
            else -> product.defaultGrams ?: 300.0
        }
    }

    var quantityPcs by remember(product.id) { mutableStateOf(1.0) }
    var weightGrams by remember(product.id) {
        mutableStateOf(
            if (isPcsItem) (product.defaultGrams ?: 12.0)
            else minOf(product.defaultGrams ?: 100.0, maxGrams)
        )
    }

    // One piece as the fridge estimated it. defaultGrams agrees for stock, but
    // for a piece item it is the only figure that means «one», so say so.
    // For a meal prep this is one container, which is what defaultGrams already
    // holds; a batch has no piece weight and must not borrow one.
    val baseGrams = (pieceGrams.takeIf { isPcsItem && !isMealPrep }
        ?: product.defaultGrams ?: 100.0).coerceAtLeast(1.0)
    val effectiveGrams = if (isPcsItem) quantityPcs * baseGrams else weightGrams
    val ratio = effectiveGrams / baseGrams

    val currentKcal = (product.kcal ?: 0.0) * ratio
    val currentCarbs = (product.carbsG ?: 0.0) * ratio
    val currentProtein = (product.proteinG ?: 0.0) * ratio
    val currentFat = (product.fatG ?: 0.0) * ratio

    val imageModel = rememberApiImageModel(product.imageUrl)

    Column(
        modifier = modifier
            .testTag("product-portion-picker")
            .background(GT.colors.bg)
            .padding(horizontal = 18.dp)
            .navigationBarsPadding(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Назад к поиску",
                modifier = Modifier
                    .heightIn(min = 44.dp)
                    .clickable(onClick = onBack)
                    .padding(vertical = 14.dp),
                color = GT.colors.ink2,
                style = GT.type.sansLabel,
            )
            Text(
                text = stringResource(R.string.manual_entry_cancel),
                modifier = Modifier
                    .heightIn(min = 44.dp)
                    .clickable(onClick = onCancel)
                    .padding(vertical = 14.dp),
                color = GT.colors.muted,
                style = GT.type.sansLabel,
            )
        }
        GTHairlineDivider()
        Spacer(Modifier.height(12.dp))

        if (imageModel != null) {
            AsyncImage(
                model = imageModel,
                contentDescription = product.name,
                // A shop's photograph is an object standing on white — a
                // bottle, a tub — and cropping it to a wide strip showed the
                // rim of the kefir and nothing else. Fit keeps the whole
                // silhouette, which is the only part that answers «это оно?».
                // A dish you photographed yourself fills its frame already,
                // so that one still crops.
                contentScale = photoContentScale(product.imageUrl),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(160.dp)
                    .background(GT.colors.surface, GT.shapes.card)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card)
                    .padding(8.dp),
            )
            Spacer(Modifier.height(10.dp))
        }

        if (isMealPrep && onPhotoTaken != null) {
            MealPrepPhotoButton(
                hasPhoto = imageModel != null,
                onCaptured = { path, onResult -> onPhotoTaken(product.id, path, onResult) },
            )
            Spacer(Modifier.height(10.dp))
        }

        Text(
            text = product.name,
            color = GT.colors.ink,
            style = GT.type.serifSection,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        product.subtitle?.let { sub ->
            Text(
                text = sub,
                modifier = Modifier.padding(top = 2.dp),
                color = if (isMealPrep) GT.colors.good else if (isFridge) GT.colors.accent else GT.colors.muted,
                style = GT.type.kicker,
                maxLines = 1,
            )
        }

        Spacer(Modifier.height(16.dp))

        // Nothing left to record. The list drops a depleted lot on the next
        // refresh, but a card opened from a stale one used to offer a portion
        // of nothing — «0.0 шт в наличии» above a slider that wrote 0,8 г
        // into the diary.
        val soldOut = product.isStock && !isMealPrep && (remainingGrams ?: 1.0) < 1.0
        if (soldOut) {
            Text(
                text = "Закончилось",
                color = GT.colors.ink,
                style = GT.type.sansLabel,
            )
            Text(
                text = "В холодильнике этого больше нет",
                modifier = Modifier.padding(top = 2.dp),
                color = GT.colors.muted,
                style = GT.type.kicker,
            )
            Spacer(Modifier.height(14.dp))
            return@Column
        }

        val unanswered = product.needsServingUnit && chosenUnit == null
        if (unanswered) {
            ServingUnitQuestion(
                pieceGrams = pieceGrams,
                onAnswer = { unit ->
                    chosenUnit = unit
                    onServingUnitChosen?.invoke(product.id, unit)
                },
            )
        } else if (isPcsItem) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Количество:",
                    color = GT.colors.muted,
                    style = GT.type.kicker,
                )
                Text(
                    text = if (quantityPcs % 1.0 == 0.0) {
                        "${countLabel(quantityPcs.toInt(), isMealPrep)} (${effectiveGrams.roundToInt()} г)"
                    } else {
                        "$quantityPcs шт (${effectiveGrams.roundToInt()} г)"
                    },
                    color = GT.colors.ink,
                    style = GT.type.monoLabel,
                )
            }
            val maxPcsFloat = maxOf(maxPcs.toFloat(), 1f)
            if (maxPcsFloat > 1f) {
                Slider(
                    value = quantityPcs.toFloat(),
                    onValueChange = { quantityPcs = (Math.round(it)).toDouble().coerceIn(1.0, maxPcs) },
                    valueRange = 1f..maxPcsFloat,
                    steps = (maxPcsFloat.toInt() - 2).coerceAtLeast(0),
                    colors = SliderDefaults.colors(
                        thumbColor = GT.colors.ink,
                        activeTrackColor = GT.colors.ink,
                        inactiveTrackColor = GT.colors.hairline2,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp)
                    // «2 контейнера» is three times the width of «2 шт», and
                    // three of them do not fit a phone. Let the row slide
                    // rather than clip the last choice off the screen.
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                val chipOptions = when {
                    maxPcs <= 1.0 -> listOf(1.0)
                    maxPcs == 2.0 -> listOf(1.0, 2.0)
                    maxPcs == 3.0 -> listOf(1.0, 2.0, 3.0)
                    else -> listOf(1.0, 2.0, maxPcs)
                }.distinct()

                chipOptions.forEach { q ->
                    val isSel = (quantityPcs == q)
                    val label = if (q == maxPcs && maxPcs > 2.0) {
                        "Все (${countLabel(q.toInt(), isMealPrep)})"
                    } else {
                        countLabel(q.toInt(), isMealPrep)
                    }
                    Box(
                        modifier = Modifier
                            .background(if (isSel) GT.colors.ink else GT.colors.surface, RoundedCornerShape(6.dp))
                            .border(GT.space.hairline, if (isSel) GT.colors.ink else GT.colors.hairline2, RoundedCornerShape(6.dp))
                            .clickable { quantityPcs = q }
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                    ) {
                        Text(
                            text = label,
                            color = if (isSel) GT.colors.bg else GT.colors.ink,
                            style = GT.type.monoLabel,
                        )
                    }
                }
            }
        } else {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Вес порции:",
                    color = GT.colors.muted,
                    style = GT.type.kicker,
                )
                Text(
                    text = "${weightGrams.roundToInt()} г",
                    color = GT.colors.ink,
                    style = GT.type.monoLabel,
                )
            }
            val minGram = minOf(20f, maxGrams.toFloat())
            // The track ends where the stock does. It used to be floored at
            // 200 g, so a lot with 80 g left drew a slider two and a half
            // times longer than the thumb could travel.
            val maxGram = maxGrams.toFloat()
            if (maxGram > minGram) {
                Slider(
                    value = weightGrams.toFloat().coerceIn(minGram, maxGram),
                    onValueChange = { weightGrams = (Math.round(it / 10.0) * 10.0).coerceIn(minGram.toDouble(), maxGrams) },
                    valueRange = minGram..maxGram,
                    steps = (((maxGram - minGram) / 10f).toInt() - 1).coerceAtLeast(0),
                    colors = SliderDefaults.colors(
                        thumbColor = GT.colors.ink,
                        activeTrackColor = GT.colors.ink,
                        inactiveTrackColor = GT.colors.hairline2,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                val gramChips = listOf(50.0, 100.0, 150.0, 200.0).filter { it <= maxGrams }
                gramChips.forEach { w ->
                    val isSel = (weightGrams == w)
                    Box(
                        modifier = Modifier
                            .background(if (isSel) GT.colors.ink else GT.colors.surface, RoundedCornerShape(6.dp))
                            .border(GT.space.hairline, if (isSel) GT.colors.ink else GT.colors.hairline2, RoundedCornerShape(6.dp))
                            .clickable { weightGrams = w }
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                    ) {
                        Text(
                            text = "${w.toInt()} г",
                            color = if (isSel) GT.colors.bg else GT.colors.ink,
                            style = GT.type.monoLabel,
                        )
                    }
                }
                if (maxGrams > 0 && !gramChips.contains(maxGrams)) {
                    val isSel = (weightGrams == maxGrams)
                    Box(
                        modifier = Modifier
                            .background(if (isSel) GT.colors.ink else GT.colors.surface, RoundedCornerShape(6.dp))
                            .border(GT.space.hairline, if (isSel) GT.colors.ink else GT.colors.hairline2, RoundedCornerShape(6.dp))
                            .clickable { weightGrams = maxGrams }
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                    ) {
                        Text(
                            text = "Вся (${maxGrams.roundToInt()} г)",
                            color = if (isSel) GT.colors.bg else GT.colors.ink,
                            style = GT.type.monoLabel,
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(GT.colors.surface, RoundedCornerShape(8.dp))
                .border(GT.space.hairline, GT.colors.hairline, RoundedCornerShape(8.dp))
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceAround,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("ККАЛ", style = GT.type.kicker, color = GT.colors.muted)
                Text(currentKcal.roundToInt().toString(), style = GT.type.monoNumber, color = GT.colors.ink)
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("УГЛЕВОДЫ", style = GT.type.kicker, color = GT.colors.muted)
                Text("${(Math.round(currentCarbs * 10.0) / 10.0)} г", style = GT.type.monoNumber, color = GT.colors.ink)
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("БЕЛКИ", style = GT.type.kicker, color = GT.colors.muted)
                Text("${(Math.round(currentProtein * 10.0) / 10.0)} г", style = GT.type.monoNumber, color = GT.colors.ink)
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("ЖИРЫ", style = GT.type.kicker, color = GT.colors.muted)
                Text("${(Math.round(currentFat * 10.0) / 10.0)} г", style = GT.type.monoNumber, color = GT.colors.ink)
            }
        }

        Spacer(Modifier.height(18.dp))

        val servingLabel = when {
            isPcsItem && quantityPcs % 1.0 == 0.0 -> countLabel(quantityPcs.toInt(), isMealPrep)
            isPcsItem -> "$quantityPcs шт"
            else -> "${effectiveGrams.roundToInt()} г"
        }
        val actionText = if (isFridge || isMealPrep) "Списать и записать · $servingLabel" else "Записать · $servingLabel"

        if (unanswered) {
            Spacer(Modifier.height(14.dp))
            return@Column
        }

        GTOutlineButton(
            text = "$actionText (${currentKcal.roundToInt()} ккал)",
            onClick = {
                onSubmit(
                    product,
                    effectiveGrams,
                    servingLabel,
                    quantityPcs.toInt().takeIf { isMealPrep },
                )
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
        )
        Spacer(Modifier.height(14.dp))
    }
}
