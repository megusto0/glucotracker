package com.local.glucotracker.data.sync

import com.local.glucotracker.domain.model.OutboxItem
import com.local.glucotracker.domain.model.OutboxKind
import javax.inject.Inject
import javax.inject.Singleton

enum class ConflictStrategy {
    KeepLocal,
    KeepServer,
    KeepBoth,
}

sealed interface ConflictResolution {
    data class RetryLocal(val kind: OutboxKind) : ConflictResolution
    data class UseServer(val serverId: String?) : ConflictResolution
    data class CreateBoth(val kind: OutboxKind) : ConflictResolution
}

@Singleton
class ConflictResolver @Inject constructor() {
    fun resolve(item: OutboxItem, strategy: ConflictStrategy): ConflictResolution =
        when (strategy) {
            ConflictStrategy.KeepLocal -> ConflictResolution.RetryLocal(item.kind)
            ConflictStrategy.KeepServer -> ConflictResolution.UseServer(item.serverIdOnSuccess)
            ConflictStrategy.KeepBoth -> ConflictResolution.CreateBoth(item.kind)
        }
}
