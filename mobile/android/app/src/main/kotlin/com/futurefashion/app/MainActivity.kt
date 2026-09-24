package com.futurefashion.app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * Hosts the Flutter app and one small native helper: copying the installed
 * APK to a shareable file, for "Share App + Referral". It reads only this
 * app's own package file and needs no storage permission.
 */
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "futurefashion/apk")
            .setMethodCallHandler { call, result ->
                if (call.method != "prepareApk") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val requested = call.argument<String>("fileName") ?: "FutureFashion.apk"
                val fileName = requested.replace(Regex("[^A-Za-z0-9._-]"), "_")
                Thread {
                    val path: String? = try {
                        val info = applicationContext.applicationInfo
                        // Installed from a store as split APKs: the base file alone
                        // won't install, so the app shares a download link instead.
                        if (!info.splitSourceDirs.isNullOrEmpty()) {
                            null
                        } else {
                            val folder = File(cacheDir, "apk_share").apply { mkdirs() }
                            folder.listFiles()?.forEach { it.delete() }
                            val target = File(folder, fileName)
                            File(info.sourceDir).copyTo(target, overwrite = true)
                            target.absolutePath
                        }
                    } catch (e: Exception) {
                        null
                    }
                    runOnUiThread { result.success(path) }
                }.start()
            }
    }
}
