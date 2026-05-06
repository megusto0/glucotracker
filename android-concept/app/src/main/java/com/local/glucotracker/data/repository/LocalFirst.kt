package com.local.glucotracker.data.repository

import com.local.glucotracker.domain.model.CachedView
import com.local.glucotracker.domain.model.Source
import java.util.logging.Logger
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant

private val localFirstLogger = Logger.getLogger("LocalFirst")

fun <T> localFirst(
    cache: () -> Flow<T?>,
    refresh: suspend () -> Unit,
    now: () -> Instant = { Clock.System.now() },
): Flow<CachedView<T>> =
    flow {
        val initial = cache().first()
        val initialSource = initial.toSource()

        emit(
            CachedView(
                value = initial,
                fetchedAt = null,
                isRefreshing = false,
                source = initialSource,
            ),
        )
        emit(
            CachedView(
                value = initial,
                fetchedAt = null,
                isRefreshing = true,
                source = initialSource,
            ),
        )

        val refreshResult = runCatching { refresh() }
        if (refreshResult.isSuccess) {
            val refreshed = cache().first()
            emit(
                CachedView(
                    value = refreshed,
                    fetchedAt = now(),
                    isRefreshing = false,
                    source = refreshed.toNetworkOrEmpty(),
                ),
            )
        } else {
            localFirstLogger.warning(refreshResult.exceptionOrNull()?.message ?: "Local-first refresh failed")
            emit(
                CachedView(
                    value = initial,
                    fetchedAt = null,
                    isRefreshing = false,
                    source = initialSource,
                ),
            )
        }

        emitAllCacheUpdates(cache().drop(1))
    }

private suspend fun <T> kotlinx.coroutines.flow.FlowCollector<CachedView<T>>.emitAllCacheUpdates(
    updates: Flow<T?>,
) {
    updates
        .map { value ->
            CachedView(
                value = value,
                fetchedAt = null,
                isRefreshing = false,
                source = value.toSource(),
            )
        }
        .collect { emit(it) }
}

private fun <T> T?.toSource(): Source = if (this == null) Source.Empty else Source.Cache
private fun <T> T?.toNetworkOrEmpty(): Source = if (this == null) Source.Empty else Source.Network
