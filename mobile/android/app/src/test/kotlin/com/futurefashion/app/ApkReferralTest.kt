package com.futurefashion.app

import com.android.apksig.ApkSigner
import com.android.apksig.ApkVerifier
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files
import java.security.KeyStore
import java.security.PrivateKey
import java.security.cert.X509Certificate
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.BeforeClass
import org.junit.Test

/**
 * A shared APK must install and update exactly like the original. Google's own
 * verifier (apksig, the library behind apksigner) checks every copy here.
 */
class ApkReferralTest {
    companion object {
        private lateinit var dir: File
        private lateinit var signed: File

        @BeforeClass
        @JvmStatic
        fun signTestApk() {
            dir = Files.createTempDirectory("apkref").toFile()
            val (key, cert) = throwawayKey(dir)
            val unsigned = File(dir, "unsigned.apk")
            ZipOutputStream(unsigned.outputStream()).use { zip ->
                for ((name, size) in listOf("AndroidManifest.xml" to 900, "classes.dex" to 70_000, "res/raw/intro.txt" to 3_000)) {
                    zip.putNextEntry(ZipEntry(name))
                    zip.write(ByteArray(size) { (it * 31 + name.length).toByte() })
                    zip.closeEntry()
                }
            }
            signed = File(dir, "signed.apk")
            ApkSigner.Builder(listOf(ApkSigner.SignerConfig.Builder("test", key, listOf(cert)).build()))
                .setInputApk(unsigned)
                .setOutputApk(signed)
                .setMinSdkVersion(24)
                .setV1SigningEnabled(false)
                .setV2SigningEnabled(true)
                .setV3SigningEnabled(true)
                .build()
                .sign()
        }

        /** A key made for this test run only (keytool ships with the JDK). */
        private fun throwawayKey(dir: File): Pair<PrivateKey, X509Certificate> {
            val store = File(dir, "test.p12")
            val keytool = File(System.getProperty("java.home"), "bin/keytool").path
            val process = ProcessBuilder(
                keytool, "-genkeypair", "-keystore", store.path, "-storetype", "PKCS12", "-storepass", "throwaway",
                "-alias", "test", "-keyalg", "RSA", "-keysize", "2048", "-validity", "2", "-dname", "CN=ApkReferralTest",
            ).redirectErrorStream(true).start()
            val output = process.inputStream.bufferedReader().readText()
            check(process.waitFor() == 0) { "keytool failed: $output" }
            val keyStore = KeyStore.getInstance("PKCS12")
            store.inputStream().use { keyStore.load(it, "throwaway".toCharArray()) }
            val key = keyStore.getKey("test", "throwaway".toCharArray()) as PrivateKey
            return key to (keyStore.getCertificate("test") as X509Certificate)
        }

        private fun verify(apk: File): ApkVerifier.Result =
            ApkVerifier.Builder(apk).setMinCheckedPlatformVersion(24).setMaxCheckedPlatformVersion(35).build().verify()

        /** Size of the APK Signing Block, from the file's own ZIP records. */
        private fun signingBlockSize(apk: File): Long {
            val bytes = apk.readBytes()
            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            val eocd = (bytes.size - 22 downTo 0).first { buffer.getInt(it) == 0x06054b50 }
            val cdOffset = buffer.getInt(eocd + 16).toLong()
            return buffer.getLong((cdOffset - 24).toInt()) + 8
        }
    }

    @Test
    fun theTestApkIsProperlySigned() {
        val result = verify(signed)
        assertTrue(result.errors.toString(), result.isVerified)
        assertNull(ApkReferral.read(signed))
    }

    @Test
    fun aCopyCarriesTheCodeAndStillVerifies() {
        val copy = File(dir, "shared.apk")
        ApkReferral.embed(signed, copy, "7Q2K9MXA")

        val result = verify(copy)
        assertTrue(result.errors.toString(), result.isVerified)
        assertTrue(result.isVerifiedUsingV2Scheme && result.isVerifiedUsingV3Scheme)
        assertEquals("7Q2K9MXA", ApkReferral.read(copy))
        // Same signing certificate, so updates signed with the release key install over it.
        assertEquals(verify(signed).signerCertificates, result.signerCertificates)
        // The app inside is byte-for-byte the same.
        ZipFile(signed).use { original ->
            ZipFile(copy).use { shared ->
                for (entry in original.entries()) {
                    assertTrue(original.getInputStream(entry).readBytes().contentEquals(shared.getInputStream(shared.getEntry(entry.name)).readBytes()))
                }
            }
        }
    }

    @Test
    fun resharingReplacesTheCode() {
        val first = File(dir, "first.apk")
        val second = File(dir, "second.apk")
        ApkReferral.embed(signed, first, "7Q2K9MXA")
        ApkReferral.embed(first, second, "K3M9P2QA")
        assertEquals("K3M9P2QA", ApkReferral.read(second))
        assertTrue(verify(second).isVerified)
        assertEquals(first.length(), second.length()) // replaced, not appended
    }

    @Test
    fun theSigningBlockStaysPageAlignedWhenItWas() {
        val copy = File(dir, "aligned.apk")
        ApkReferral.embed(signed, copy, "7Q2K9MXA")
        if (signingBlockSize(signed) % 4096 == 0L) {
            assertEquals(0L, signingBlockSize(copy) % 4096)
        }
    }

    @Test
    fun onlyRealCodesAreWrittenOrRead() {
        val copy = File(dir, "bad.apk")
        for (bad in listOf("", "short", "7q2k9mxa", "O0I1L5UA", "7Q2K9MXA7", "<script>")) {
            try {
                ApkReferral.embed(signed, copy, bad)
                throw AssertionError("accepted $bad")
            } catch (expected: IllegalArgumentException) {
            }
        }
        assertNull(ApkReferral.read(File(dir, "missing.apk")))
        val junk = File(dir, "junk.apk").apply { writeBytes(ByteArray(5000) { it.toByte() }) }
        assertNull(ApkReferral.read(junk))
    }

    @Test(expected = ApkReferral.NotSignedApkException::class)
    fun anUnsignedApkIsRefused() {
        ApkReferral.embed(File(dir, "unsigned.apk"), File(dir, "never.apk"), "7Q2K9MXA")
    }

    /** Run with -PrealApk=/path/to/app-prod-release.apk to check a real build. */
    @Test
    fun theRealReleaseApkStillVerifies() {
        val path = System.getProperty("ff.realApk")
        assumeTrue("no real APK given", !path.isNullOrBlank())
        val real = File(path!!)
        val copy = File(dir, "real-shared.apk")
        ApkReferral.embed(real, copy, "7Q2K9MXA")
        val result = verify(copy)
        assertTrue(result.errors.toString(), result.isVerified)
        assertEquals(verify(real).signerCertificates, result.signerCertificates)
        assertEquals("7Q2K9MXA", ApkReferral.read(copy))
        if (signingBlockSize(real) % 4096 == 0L) assertEquals(0L, signingBlockSize(copy) % 4096)
    }
}
