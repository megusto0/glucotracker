package com.local.glucotracker.ui.feature.capture

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
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
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
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
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.data.repository.BrandPrefix
import com.local.glucotracker.data.repository.parsePrefix
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.format.formatKcal
import kotlinx.coroutines.delay

private sealed interface ComposeSuggestion {
    val id: String
    val name: String
    val kcal: Double?
    val usageCount: Int

    data class ProductSuggestion(val product: Product) : ComposeSuggestion {
        override val id = "product:${product.id}"
        override val name = product.name
        override val kcal = product.kcal
        override val usageCount = product.usageCount
    }

    data class TemplateSuggestion(val template: Template) : ComposeSuggestion {
        override val id = "template:${template.id}"
        override val name = template.name
        override val kcal = template.defaultKcal
        override val usageCount = template.usageCount
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
    modifier: Modifier = Modifier,
    initialText: String = "",
    initialProducts: List<Product> = emptyList(),
    initialTemplates: List<Template> = emptyList(),
) {
    var text by remember { mutableStateOf(initialText) }
    var products by remember { mutableStateOf(initialProducts) }
    var templates by remember { mutableStateOf(initialTemplates) }
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
        (templates.map { ComposeSuggestion.TemplateSuggestion(it) } +
            products.map { ComposeSuggestion.ProductSuggestion(it) })
            .sortedWith(
                compareByDescending<ComposeSuggestion> { it.name.startsWith(query, ignoreCase = true) }
                    .thenByDescending { it.usageCount }
                    .thenBy { it.name },
            )
    }
    val hasExactMatch = suggestions.any { it.name.equals(query, ignoreCase = true) }
    val canSubmitFreeform = query.isNotBlank() && !hasExactMatch

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
        Text(
            text = item.name,
            modifier = Modifier.weight(1f),
            color = GT.colors.ink,
            style = GT.type.sansLabel,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
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
