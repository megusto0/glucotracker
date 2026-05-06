-keepattributes *Annotation*
-keepattributes SourceFile,LineNumberTable
-keep public class * extends java.lang.Exception

-keep class kotlinx.serialization.** { *; }
-keepclassmembers class kotlinx.serialization.** { *; }

-keep class com.local.glucotracker.data.local.entity.** { *; }
-keep class com.local.glucotracker.data.remote.dto.** { *; }

-dontwarn kotlinx.serialization.**
