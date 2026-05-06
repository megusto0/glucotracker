package com.local.glucotracker.ui.navigation

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTBottomBar
import com.local.glucotracker.ui.design.primitives.GTBottomBarItem
import com.local.glucotracker.ui.design.primitives.GTFab
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTKicker
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.feature.base.BaseRoute
import com.local.glucotracker.ui.feature.capture.CaptureViewModel
import com.local.glucotracker.ui.feature.capture.DraftRoute
import com.local.glucotracker.ui.feature.capture.PhotoCaptureScreen
import com.local.glucotracker.ui.feature.capture.TemplatePickerScreen
import com.local.glucotracker.ui.feature.capture.TextInputScreen
import com.local.glucotracker.ui.feature.glucose.GlucoseRoute
import com.local.glucotracker.ui.feature.history.HistoryRoute
import com.local.glucotracker.ui.feature.more.MoreRoute
import com.local.glucotracker.ui.feature.record.RecordRoute
import com.local.glucotracker.ui.feature.stats.StatsRoute
import com.local.glucotracker.ui.feature.today.TodayRoute

@Composable
fun GlucotrackerApp(
    offlineBannerViewModel: OfflineBannerViewModel = hiltViewModel(),
) {
    val offlineBannerState by offlineBannerViewModel.state.collectAsState()
    MainScaffold(offlineBannerState = offlineBannerState)
}

@Composable
fun MainScaffold(
    offlineBannerState: OfflineBannerUiState,
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController(),
    navHost: (@Composable (Modifier, NavHostController) -> Unit)? = null,
) {
    var captureSheetVisible by remember { mutableStateOf(false) }
    var lastQueuedOutboxId by rememberSaveable { mutableStateOf<String?>(null) }
    val currentBackStack by navController.currentBackStackEntryAsState()
    val selectedRoute = currentBackStack?.destination?.route?.toBottomRoute() ?: Route.Today.route
    val navigateToTodayWithQueuedOutbox: (String) -> Unit = { outboxId ->
        lastQueuedOutboxId = outboxId
        captureSheetVisible = false
        navController.navigate(Route.Today.route) {
            popUpTo(Route.Today.route) {
                saveState = true
            }
            launchSingleTop = true
            restoreState = true
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .statusBarsPadding(),
    ) {
        GTOfflineBanner(state = offlineBannerState)
        Scaffold(
            containerColor = GT.colors.bg,
            bottomBar = {
                MainBottomBar(
                    selectedRoute = selectedRoute,
                    onRouteClick = { route ->
                        navController.navigate(route) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onCaptureClick = { captureSheetVisible = true },
                )
            },
        ) { innerPadding ->
            val contentModifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
            if (navHost == null) {
                GTNavHost(
                    navController = navController,
                    lastQueuedOutboxId = lastQueuedOutboxId,
                    onQueuedOutboxConsumed = { consumedId ->
                        if (lastQueuedOutboxId == consumedId) {
                            lastQueuedOutboxId = null
                        }
                    },
                    onOutboxQueued = navigateToTodayWithQueuedOutbox,
                    modifier = contentModifier,
                )
            } else {
                navHost(contentModifier, navController)
            }
        }
    }

    if (captureSheetVisible) {
        CaptureSheet(
            onDismiss = { captureSheetVisible = false },
            onNavigate = { route -> navController.navigate(route) },
            onOutboxQueued = navigateToTodayWithQueuedOutbox,
        )
    }
}

@Composable
fun GTNavHost(
    navController: NavHostController,
    lastQueuedOutboxId: String? = null,
    onQueuedOutboxConsumed: (String) -> Unit = {},
    onOutboxQueued: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = Route.Today.route,
        modifier = modifier,
        enterTransition = { EnterTransition.None },
        exitTransition = { ExitTransition.None },
        popEnterTransition = { EnterTransition.None },
        popExitTransition = { ExitTransition.None },
    ) {
        composable(Route.Today.route) {
            TodayStatsPager(
                onOpenRecord = { id -> navController.navigate(Route.Record(id).route) },
                onOpenDraft = { outboxId -> navController.navigate(Route.Draft(outboxId).route) },
                lastQueuedOutboxId = lastQueuedOutboxId,
                onQueuedOutboxConsumed = onQueuedOutboxConsumed,
            )
        }
        composable(Route.Glucose.route) {
            GlucoseRoute()
        }
        composable(Route.History.route) {
            HistoryRoute(
                onOpenRecord = { id -> navController.navigate(Route.Record(id).route) },
            )
        }
        composable(Route.Base.route) {
            BaseRoute(
                onOutboxQueued = onOutboxQueued,
            )
        }
        composable(Route.More.route) {
            MoreRoute(
                onOpenBase = {
                    navController.navigate(Route.Base.route) {
                        launchSingleTop = true
                    }
                },
            )
        }
        composable(
            route = Route.Record.Pattern,
            arguments = listOf(navArgument(Route.Record.ArgId) { type = NavType.StringType }),
            enterTransition = { recordEnterTransition() },
            popEnterTransition = { recordEnterTransition() },
            exitTransition = { fadeOut(animationSpec = tween(120)) },
            popExitTransition = { fadeOut(animationSpec = tween(120)) },
        ) { entry ->
            val id = entry.arguments?.getString(Route.Record.ArgId).orEmpty()
            RecordRoute(
                id = id,
                onClose = { navController.popBackStack() },
                onOpenGlucose = {
                    navController.navigate(Route.Glucose.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        }
        composable(Route.PhotoCapture.route) {
            PhotoCaptureScreen(
                onPhotoQueued = { outboxId ->
                    onOutboxQueued(outboxId)
                },
                onClose = { navController.popBackStack() },
            )
        }
        composable(
            route = Route.Draft.Pattern,
            arguments = listOf(navArgument(Route.Draft.ArgOutboxId) { type = NavType.StringType }),
            enterTransition = { recordEnterTransition() },
            popEnterTransition = { recordEnterTransition() },
            exitTransition = { fadeOut(animationSpec = tween(120)) },
            popExitTransition = { fadeOut(animationSpec = tween(120)) },
        ) { entry ->
            val outboxId = entry.arguments?.getString(Route.Draft.ArgOutboxId).orEmpty()
            DraftRoute(
                outboxId = outboxId,
                onFinished = { navController.popBackStack() },
            )
        }
        composable(Route.TextInput.route) {
            TextInputScreen(onFinished = { navController.popBackStack() })
        }
        composable(Route.TemplatePicker.route) {
            TemplatePickerScreen(onFinished = { navController.popBackStack() })
        }
    }
}

@Composable
fun GTOfflineBanner(
    state: OfflineBannerUiState,
    modifier: Modifier = Modifier,
) {
    if (state == OfflineBannerUiState.Hidden) return

    val message = when (state) {
        OfflineBannerUiState.Hidden -> ""
        is OfflineBannerUiState.SyncQueue -> stringResource(R.string.offline_banner_sync_queue, state.queueDepth)
        is OfflineBannerUiState.OfflineStale -> stringResource(R.string.offline_banner_stale, state.dataAt)
        is OfflineBannerUiState.OfflineQueue -> stringResource(R.string.offline_banner_queue, state.queueDepth)
    }
    val tone = when (state) {
        is OfflineBannerUiState.OfflineQueue,
        is OfflineBannerUiState.OfflineStale,
        -> GT.colors.warn
        else -> GT.colors.muted
    }
    val hairlineColor = GT.colors.hairline
    val hairlineWidth = GT.space.hairline
    val monoStyle = GT.type.monoLabel
    val annotated = buildAnnotatedString {
        append(message)
        if (state is OfflineBannerUiState.OfflineStale) {
            val start = message.indexOf(state.dataAt)
            if (start >= 0) {
                addStyle(
                    SpanStyle(
                        fontFamily = monoStyle.fontFamily,
                        fontSize = monoStyle.fontSize,
                        fontWeight = monoStyle.fontWeight,
                    ),
                    start = start,
                    end = start + state.dataAt.length,
                )
            }
        }
    }

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(24.dp)
            .background(GT.colors.surface)
            .drawBehind {
                drawLine(
                    color = hairlineColor,
                    start = Offset(0f, size.height),
                    end = Offset(size.width, size.height),
                    strokeWidth = hairlineWidth.toPx(),
                )
            }
            .padding(horizontal = 14.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(
            text = annotated,
            color = tone,
            style = GT.type.sansLabel,
            maxLines = 1,
        )
    }
}

@Composable
private fun TodayStatsPager(
    onOpenRecord: (String) -> Unit,
    onOpenDraft: (String) -> Unit,
    lastQueuedOutboxId: String?,
    onQueuedOutboxConsumed: (String) -> Unit,
) {
    val pagerState = rememberPagerState(pageCount = { 2 })
    Column(Modifier.fillMaxSize()) {
        PagerKicker(
            selectedPage = pagerState.currentPage,
            labels = listOf(
                stringResource(R.string.today_page_label),
                stringResource(R.string.stats_page_label),
            ),
            hint = if (pagerState.currentPage == 0) {
                stringResource(R.string.pager_today_hint)
            } else {
                stringResource(R.string.pager_stats_hint)
            },
        )
        HorizontalPager(
            state = pagerState,
            modifier = Modifier.fillMaxSize(),
        ) { page ->
            when (page) {
                0 -> TodayRoute(
                    onOpenRecord = onOpenRecord,
                    onOpenDraft = onOpenDraft,
                    lastQueuedOutboxId = lastQueuedOutboxId,
                    onQueuedOutboxConsumed = onQueuedOutboxConsumed,
                )
                else -> StatsRoute()
            }
        }
    }
}

@Composable
private fun PagerKicker(
    selectedPage: Int,
    labels: List<String>,
    hint: String,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            labels.forEachIndexed { index, _ ->
                Box(
                    modifier = Modifier
                        .size(if (index == selectedPage) 6.dp else 4.dp)
                        .background(
                            color = if (index == selectedPage) GT.colors.ink else GT.colors.hairline2,
                            shape = CircleShape,
                        ),
                )
            }
        }
        Spacer(Modifier.size(8.dp))
        GTKicker(text = labels[selectedPage])
        Spacer(Modifier.weight(1f))
        Text(
            text = hint,
            color = GT.colors.muted,
            style = GT.type.kicker,
            maxLines = 1,
        )
    }
}

@Composable
private fun PlaceholderScreen(title: String) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(18.dp),
    ) {
        Text(
            text = title,
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        GTHintBox(
            text = stringResource(R.string.desktop_only_hint),
            modifier = Modifier.padding(top = 18.dp),
        )
    }
}

@Composable
private fun RecordPlaceholder(id: String) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(18.dp),
    ) {
        Text(
            text = stringResource(R.string.record_title),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
        )
        Text(
            text = id,
            modifier = Modifier.padding(top = 8.dp),
            color = GT.colors.muted,
            style = GT.type.monoLabel,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CaptureSheet(
    onDismiss: () -> Unit,
    onNavigate: (String) -> Unit,
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
    val openGalleryPicker = {
        galleryLauncher.launch(
            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
        )
    }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = GT.colors.bg,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .testTag("capture-sheet")
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 18.dp, vertical = 20.dp),
        ) {
            Text(
                text = stringResource(R.string.capture_sheet_title),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
            Spacer(Modifier.height(14.dp))
            CaptureOptionRow(
                title = stringResource(R.string.capture_photo_title),
                subtitle = stringResource(R.string.capture_photo_subtitle),
                kind = CaptureOptionKind.Photo,
                onClick = {
                    onDismiss()
                    onNavigate(Route.PhotoCapture.route)
                },
            )
            CaptureOptionRow(
                title = stringResource(R.string.capture_gallery_title),
                subtitle = stringResource(R.string.capture_gallery_subtitle),
                kind = CaptureOptionKind.Gallery,
                onClick = {
                    openGalleryPicker()
                },
            )
            CaptureOptionRow(
                title = stringResource(R.string.capture_text_title),
                subtitle = stringResource(R.string.capture_text_subtitle),
                kind = CaptureOptionKind.Text,
                onClick = {
                    onDismiss()
                    onNavigate(Route.TextInput.route)
                },
            )
            CaptureOptionRow(
                title = stringResource(R.string.capture_template_title),
                subtitle = stringResource(R.string.capture_template_subtitle),
                kind = CaptureOptionKind.Template,
                onClick = {
                    onDismiss()
                    onNavigate(Route.TemplatePicker.route)
                },
            )
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                GTKicker(
                    text = stringResource(R.string.capture_quick_commands_title),
                    modifier = Modifier.padding(top = 8.dp),
                )
                Text(
                    text = stringResource(R.string.capture_quick_commands_body),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun CaptureOptionRow(
    title: String,
    subtitle: String,
    kind: CaptureOptionKind,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 58.dp)
            .padding(bottom = 8.dp)
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(36.dp)
                .background(GT.colors.bg, GT.shapes.iconButton)
                .border(GT.space.hairline, GT.colors.hairline2, GT.shapes.iconButton),
            contentAlignment = Alignment.Center,
        ) {
            CaptureOptionGlyph(kind = kind)
        }
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 14.dp),
        ) {
            Text(
                text = title,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = subtitle,
                modifier = Modifier.padding(top = 2.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

private enum class CaptureOptionKind {
    Photo,
    Gallery,
    Text,
    Template,
}

@Composable
private fun CaptureOptionGlyph(kind: CaptureOptionKind) {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(20.dp)) {
        val stroke = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round)
        when (kind) {
            CaptureOptionKind.Photo -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(2.dp.toPx(), 5.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(16.dp.toPx(), 11.dp.toPx()),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                    style = stroke,
                )
                drawCircle(color = color, radius = 3.dp.toPx(), center = Offset(10.dp.toPx(), 10.5.dp.toPx()), style = stroke)
                drawLine(color = color, start = Offset(7.dp.toPx(), 5.dp.toPx()), end = Offset(8.dp.toPx(), 3.dp.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
                drawLine(color = color, start = Offset(8.dp.toPx(), 3.dp.toPx()), end = Offset(12.dp.toPx(), 3.dp.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
                drawLine(color = color, start = Offset(12.dp.toPx(), 3.dp.toPx()), end = Offset(13.dp.toPx(), 5.dp.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
            }
            CaptureOptionKind.Gallery -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(3.dp.toPx(), 3.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(14.dp.toPx(), 14.dp.toPx()),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                    style = stroke,
                )
                drawLine(color = color, start = Offset(5.dp.toPx(), 15.dp.toPx()), end = Offset(8.dp.toPx(), 11.dp.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
                drawLine(color = color, start = Offset(8.dp.toPx(), 11.dp.toPx()), end = Offset(11.dp.toPx(), 13.dp.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
                drawLine(color = color, start = Offset(11.dp.toPx(), 13.dp.toPx()), end = Offset(15.dp.toPx(), 8.dp.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
                drawCircle(color = color, radius = 1.2.dp.toPx(), center = Offset(7.dp.toPx(), 7.dp.toPx()))
            }
            CaptureOptionKind.Text -> {
                listOf(5.dp, 9.dp, 13.dp).forEach { y ->
                    drawLine(color = color, start = Offset(3.dp.toPx(), y.toPx()), end = Offset(15.dp.toPx(), y.toPx()), strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round)
                }
                drawCircle(color = color, radius = 2.4.dp.toPx(), center = Offset(16.dp.toPx(), 13.dp.toPx()), style = stroke)
            }
            CaptureOptionKind.Template -> {
                listOf(3.dp, 11.dp).forEach { x ->
                    listOf(3.dp, 11.dp).forEach { y ->
                        drawRoundRect(
                            color = color,
                            topLeft = Offset(x.toPx(), y.toPx()),
                            size = androidx.compose.ui.geometry.Size(6.dp.toPx(), 6.dp.toPx()),
                            cornerRadius = androidx.compose.ui.geometry.CornerRadius(1.dp.toPx(), 1.dp.toPx()),
                            style = stroke,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MainBottomBar(
    selectedRoute: String,
    onRouteClick: (String) -> Unit,
    onCaptureClick: () -> Unit,
) {
    val captureDescription = stringResource(R.string.nav_capture_content_description)
    GTBottomBar(
        items = listOf(
            GTBottomBarItem(
                id = Route.Today.route,
                label = stringResource(R.string.nav_today),
                selected = selectedRoute == Route.Today.route,
            ) { NavGlyph(NavGlyphKind.Today) },
            GTBottomBarItem(
                id = Route.Glucose.route,
                label = stringResource(R.string.nav_glucose),
                selected = selectedRoute == Route.Glucose.route,
            ) { NavGlyph(NavGlyphKind.Glucose) },
            GTBottomBarItem(
                id = Route.History.route,
                label = stringResource(R.string.nav_history),
                selected = selectedRoute == Route.History.route,
            ) { NavGlyph(NavGlyphKind.History) },
            GTBottomBarItem(
                id = Route.More.route,
                label = stringResource(R.string.nav_more),
                selected = selectedRoute == Route.More.route,
            ) { NavGlyph(NavGlyphKind.More) },
        ),
        onClick = onRouteClick,
        centerSlot = {
            GTFab(
                onClick = onCaptureClick,
                modifier = Modifier
                    .padding(top = 4.dp)
                    .semantics { contentDescription = captureDescription },
            )
        },
        modifier = Modifier.navigationBarsPadding(),
    )
}

private fun String?.toBottomRoute(): String? =
    when (this) {
        Route.Today.route -> Route.Today.route
        Route.Glucose.route -> Route.Glucose.route
        Route.History.route -> Route.History.route
        Route.Base.route -> Route.More.route
        Route.More.route -> Route.More.route
        else -> null
    }

private fun recordEnterTransition() =
    fadeIn(animationSpec = tween(180)) +
        slideInVertically(
            animationSpec = tween(180),
            initialOffsetY = { 8 },
        )

private enum class NavGlyphKind {
    Today,
    Glucose,
    History,
    More,
}

@Composable
private fun NavGlyph(kind: NavGlyphKind) {
    val color = GT.colors.ink2
    Canvas(modifier = Modifier.size(22.dp)) {
        val stroke = Stroke(width = 1.4.dp.toPx(), cap = StrokeCap.Round)
        when (kind) {
            NavGlyphKind.Today -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(4.dp.toPx(), 5.dp.toPx()),
                    size = androidx.compose.ui.geometry.Size(14.dp.toPx(), 13.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(4.dp.toPx(), 9.dp.toPx()), Offset(18.dp.toPx(), 9.dp.toPx()), stroke.width)
            }
            NavGlyphKind.Glucose -> {
                val path = Path().apply {
                    moveTo(2.dp.toPx(), 13.dp.toPx())
                    cubicTo(5.dp.toPx(), 5.dp.toPx(), 9.dp.toPx(), 5.dp.toPx(), 11.dp.toPx(), 12.dp.toPx())
                    cubicTo(13.dp.toPx(), 19.dp.toPx(), 18.dp.toPx(), 16.dp.toPx(), 20.dp.toPx(), 8.dp.toPx())
                }
                drawPath(path = path, color = color, style = stroke)
            }
            NavGlyphKind.History -> {
                drawCircle(
                    color = color,
                    radius = 7.dp.toPx(),
                    center = Offset(11.dp.toPx(), 11.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(11.dp.toPx(), 7.dp.toPx()), Offset(11.dp.toPx(), 12.dp.toPx()), stroke.width)
                drawLine(color, Offset(11.dp.toPx(), 12.dp.toPx()), Offset(15.dp.toPx(), 14.dp.toPx()), stroke.width)
            }
            NavGlyphKind.More -> {
                listOf(6.dp, 11.dp, 16.dp).forEach { x ->
                    drawCircle(
                        color = color,
                        radius = 1.4.dp.toPx(),
                        center = Offset(x.toPx(), 11.dp.toPx()),
                    )
                }
            }
        }
    }
}
