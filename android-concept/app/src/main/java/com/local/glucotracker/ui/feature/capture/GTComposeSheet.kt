package com.local.glucotracker.ui.feature.capture

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.compose.ui.platform.LocalContext
import java.io.File
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.add
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.data.repository.BrandPrefix
import com.local.glucotracker.data.repository.parsePrefix
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.stock.MealPrepPhotoButton
import com.local.glucotracker.ui.stock.StockTag
import com.local.glucotracker.ui.image.rememberApiImageModel
import kotlinx.coroutines.delay
import kotlin.math.floor
import kotlin.math.roundToInt

private sealed interface ComposeSuggestion {
    val id: String
    val name: String
    val kcal: Double?
    val usageCount: Int
    val imageUrl: String?
    val restaurantPrefix: String?

    data class ProductSuggestion(val product: Product) : ComposeSuggestion {
        override val id = "product:${product.id}"
        override val name = product.name
        override val kcal = product.kcal
        override val usageCount = product.usageCount
        override val imageUrl = product.imageUrl
        override val restaurantPrefix = product.brand?.takeIf {
            product.kind.equals("restaurant", ignoreCase = true)
        }
    }

    data class TemplateSuggestion(val template: Template) : ComposeSuggestion {
        override val id = "template:${template.id}"
        override val name = template.name
        override val kcal = template.defaultKcal
        override val usageCount = template.usageCount
        override val imageUrl = template.imageUrl
        override val restaurantPrefix = template.prefix.takeIf(::isRestaurantPrefix)
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
    }
}

private fun isRestaurantPrefix(prefix: String): Boolean =
    prefix.lowercase() in setOf("bk", "rostics", "vit", "mc", "kfc")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManualEntrySearchSheet(
    onDismiss: () -> Unit,
    onOutboxQueued: (String) -> Unit,
    viewModel: CaptureViewModel = hiltViewModel(),
) {
    val openCount by viewModel.composeSheetOpenCount.collectAsStateWithLifecycle(initialValue = 0)

    LaunchedEffect(Unit) {
        viewModel.onComposeSheetOpened()
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
        containerColor = GT.colors.bg,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
        scrimColor = GT.colors.ink.copy(alpha = 0.55f),
        dragHandle = { JournalDragHandle() },
        contentWindowInsets = { WindowInsets.ime.add(WindowInsets.navigationBars) },
    ) {
        ManualEntrySearchSheetContent(
            openCount = openCount,
            onDismiss = onDismiss,
            onSubmitText = { text ->
                viewModel.enqueueTextMeal(text) { outboxId ->
                    onDismiss()
                    onOutboxQueued(outboxId)
                }
            },
            onSubmitProduct = { product, weightGrams, servingText ->
                viewModel.enqueueProductMeal(product, weightGrams, servingText) { outboxId ->
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
            searchProducts = viewModel::searchProducts,
            searchTemplates = viewModel::searchTemplates,
            onMealPrepPhoto = viewModel::uploadMealPrepPhoto,
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight()
                .imePadding(),
        )
    }
}

@Composable
fun ManualEntrySearchSheetContent(
    openCount: Int,
    onDismiss: () -> Unit,
    onSubmitText: (String) -> Unit,
    onSubmitProduct: (Product, Double?, String?) -> Unit,
    onSubmitTemplate: (Template) -> Unit,
    searchProducts: (String, BrandPrefix?, (List<Product>) -> Unit) -> Unit,
    searchTemplates: (String, (List<Template>) -> Unit) -> Unit,
    modifier: Modifier = Modifier,
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
            .sortedWith(
                compareByDescending<ComposeSuggestion> { it.name.startsWith(query, ignoreCase = true) }
                    .thenByDescending { it.usageCount }
                    .thenBy { it.name },
            )
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
            onSubmit = { product, weightGrams, servingText ->
                onSubmitProduct(product, weightGrams, servingText)
            },
            modifier = modifier,
            onPhotoTaken = onMealPrepPhoto,
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
        LazyColumn(
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
                                selectedProductForPortion = item.product
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
            .sortedWith(
                compareByDescending<ComposeSuggestion> { it.name.startsWith(query, ignoreCase = true) }
                    .thenByDescending { it.usageCount }
                    .thenBy { it.name },
            )
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
        LazyColumn(modifier = Modifier.weight(1f)) {
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

@Composable
private fun ProductPortionPicker(
    product: Product,
    onBack: () -> Unit,
    onCancel: () -> Unit,
    onSubmit: (Product, Double?, String?) -> Unit,
    modifier: Modifier = Modifier,
    // Null where nothing can upload. A meal prep is cooked once and looks the
    // same in every container, so one photograph at the counter serves all of
    // them — and until now there was no way to take it from the phone at all.
    onPhotoTaken: ((productId: String, localPath: String, onResult: (String?) -> Unit) -> Unit)? = null,
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
    val isPcsItem = if (product.isStock) {
        product.isPieces || pieceGrams != null
    } else {
        // Catalogue products carry no stock, and rows cached before the fields
        // existed carry no sourceKind. Both keep the old guess.
        product.name.contains("шт", ignoreCase = true)
    }

    val maxPcs: Double = remember(product.stockRemaining, pieceGrams, product.isPieces) {
        val remaining = product.stockRemaining?.takeIf { it > 0 } ?: return@remember 3.0
        when {
            product.isPieces -> remaining
            // A weighed lot: how many whole pieces are left in it.
            pieceGrams != null -> floor(remaining / pieceGrams).coerceAtLeast(1.0)
            else -> 3.0
        }
    }
    val maxGrams: Double = remember(product.stockRemaining, product.defaultGrams) {
        if (product.isStock && !product.isPieces) {
            product.stockRemaining ?: product.defaultGrams ?: 300.0
        } else {
            product.defaultGrams ?: 300.0
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
    val baseGrams = (pieceGrams.takeIf { isPcsItem }
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
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(120.dp)
                    .background(GT.colors.surface, GT.shapes.card)
                    .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.card),
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

        if (isPcsItem) {
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
                    text = "${if (quantityPcs % 1.0 == 0.0) quantityPcs.toInt().toString() else quantityPcs.toString()} шт (${effectiveGrams.roundToInt()} г)",
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
                    .padding(top = 6.dp),
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
                    val label = if (q == maxPcs && maxPcs > 2.0) "Все (${q.toInt()} шт)" else "${q.toInt()} шт"
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
            val maxGram = maxOf(maxGrams.toFloat(), 200f)
            Slider(
                value = weightGrams.toFloat(),
                onValueChange = { weightGrams = (Math.round(it / 10.0) * 10.0).coerceIn(minGram.toDouble(), maxGrams) },
                valueRange = minGram..maxGram,
                steps = ((maxGram - minGram) / 10f).toInt() - 1,
                colors = SliderDefaults.colors(
                    thumbColor = GT.colors.ink,
                    activeTrackColor = GT.colors.ink,
                    inactiveTrackColor = GT.colors.hairline2,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
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

        val servingLabel = if (isPcsItem) {
            "${if (quantityPcs % 1.0 == 0.0) quantityPcs.toInt() else quantityPcs} шт"
        } else {
            "${effectiveGrams.roundToInt()} г"
        }
        val actionText = if (isFridge || isMealPrep) "Списать и записать · $servingLabel" else "Записать · $servingLabel"

        GTOutlineButton(
            text = "$actionText (${currentKcal.roundToInt()} ккал)",
            onClick = {
                onSubmit(product, effectiveGrams, servingLabel)
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
        )
        Spacer(Modifier.height(14.dp))
    }
}
