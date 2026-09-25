package com.futurefashion.app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * Hosts the Flutter app plus two native helpers for "Share App + Referral":
 *
 * - `prepareApk` copies this app's own installed APK into its cache, with the
 *   sharer's referral code built in (see ApkReferral), ready for Android's
 *   share sheet. It reads only this app's own package file and needs no
 *   storage permission.
 * - `embeddedReferralCode` reads the code built into the APK this copy was
 *   installed from, so signup can fill it in.
 */
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "futurefashion/apk")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "prepareApk" -> prepareApk(call.argument("fileName"), call.argument("referralCode"), result)
                    "embeddedReferralCode" -> background(result) { ApkReferral.read(File(applicationInfo.sourceDir)) }
                    else -> result.notImplemented()
                }
            }
    }

    private fun prepareApk(requestedName: String?, referralCode: String?, result: MethodChannel.Result) {
        val info = applicationContext.applicationInfo
        // A store install arrives as several split APKs; the base file alone
        // wouldn't install on another phone, so say so instead of sending it.
        if (!info.splitSourceDirs.isNullOrEmpty()) {
            result.error("SPLIT_INSTALL", "This copy of the app was installed in parts and can't be sent as one file.", null)
            return
        }
        val fileName = (requestedName ?: "FutureFashion.apk").replace(Regex("[^A-Za-z0-9._-]"), "_")
        Thread {
            try {
                val folder = File(cacheDir, "apk_share").apply { mkdirs() }
                folder.listFiles()?.forEach { it.delete() } // one shared copy at a time
                val source = File(info.sourceDir)
                val target = File(folder, fileName)
                var withCode = false
                if (referralCode != null && ApkReferral.isValidCode(referralCode)) {
                    try {
                        ApkReferral.embed(source, target, referralCode)
                        withCode = true
                    } catch (e: ApkReferral.NotSignedApkException) {
                        // Not v2-signed (unusual): send the file as it is.
                    }
                }
                if (!withCode) source.copyTo(target, overwrite = true)
                val prepared = mapOf("path" to target.absolutePath, "bytes" to target.length(), "withCode" to withCode)
                runOnUiThread { result.success(prepared) }
            } catch (e: Exception) {
                runOnUiThread { result.error("COPY_FAILED", "Couldn't prepare the app file.", null) }
            }
        }.start()
    }

    private fun background(result: MethodChannel.Result, work: () -> Any?) {
        Thread {
            val value = try {
                work()
            } catch (e: Exception) {
                null
            }
            runOnUiThread { result.success(value) }
        }.start()
    }
}
