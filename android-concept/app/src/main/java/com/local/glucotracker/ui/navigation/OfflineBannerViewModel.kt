package com.local.glucotracker.ui.navigation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.data.sync.ConnectivityObserver
import com.local.glucotracker.data.sync.NetworkStatus
import com.local.glucotracker.domain.model.OutboxState
import com.local.glucotracker.domain.repository.OutboxRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

sealed interface OfflineBannerUiState {
    data object Hidden : OfflineBannerUiState
    data class SyncQueue(val queueDepth: Int) : OfflineBannerUiState
    data class OfflineStale(val dataAt: String) : OfflineBannerUiState
    data class OfflineQueue(val queueDepth: Int) : OfflineBannerUiState

    companion object {
        fun resolve(
            isConnected: Boolean,
            queueDepth: Int,
            offlineGraceElapsed: Boolean,
            dataAt: String,
        ): OfflineBannerUiState =
            when {
                isConnected && queueDepth <= 0 -> Hidden
                isConnected -> SyncQueue(queueDepth)
                queueDepth > 0 -> OfflineQueue(queueDepth)
                offlineGraceElapsed -> OfflineStale(dataAt)
                else -> Hidden
            }
    }
}

@HiltViewModel
class OfflineBannerViewModel @Inject constructor(
    connectivityObserver: ConnectivityObserver,
    outboxRepository: OutboxRepository,
) : ViewModel() {
    val state = combine(
        connectivityObserver.observe().offlineSignals(),
        outboxRepository.observe().map { items ->
            items.count { item -> item.state.isActiveQueueState() }
        },
    ) { signal, queueDepth ->
        OfflineBannerUiState.resolve(
            isConnected = signal.status.isConnected,
            queueDepth = queueDepth,
            offlineGraceElapsed = signal.offlineGraceElapsed,
            dataAt = signal.dataAt,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = OfflineBannerUiState.Hidden,
    )
}

private data class OfflineSignal(
    val status: NetworkStatus,
    val offlineGraceElapsed: Boolean,
    val dataAt: String,
)

@OptIn(ExperimentalCoroutinesApi::class)
private fun Flow<NetworkStatus>.offlineSignals(): Flow<OfflineSignal> =
    flatMapLatest { status ->
        if (status.isConnected) {
            flow {
                emit(
                    OfflineSignal(
                        status = status,
                        offlineGraceElapsed = false,
                        dataAt = currentHourMinute(),
                    ),
                )
            }
        } else {
            val dataAt = currentHourMinute()
            flow {
                emit(
                    OfflineSignal(
                        status = status,
                        offlineGraceElapsed = false,
                        dataAt = dataAt,
                    ),
                )
                delay(60_000)
                emit(
                    OfflineSignal(
                        status = status,
                        offlineGraceElapsed = true,
                        dataAt = dataAt,
                    ),
                )
            }
        }
    }

private fun OutboxState.isActiveQueueState(): Boolean =
    this == OutboxState.Queued ||
        this == OutboxState.Sending ||
        this == OutboxState.Conflict ||
        this == OutboxState.Estimating

private fun currentHourMinute(): String {
    val time = Clock.System.now()
        .toLocalDateTime(TimeZone.currentSystemDefault())
        .time
    return "${time.hour.toString().padStart(2, '0')}:${time.minute.toString().padStart(2, '0')}"
}
