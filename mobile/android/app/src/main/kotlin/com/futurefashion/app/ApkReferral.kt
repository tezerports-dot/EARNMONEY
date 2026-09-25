package com.futurefashion.app

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel

/**
 * Carries the sharer's referral code inside a shared copy of the APK, so it
 * survives transfers that drop the message text (Bluetooth, Nearby Share,
 * Xender…).
 *
 * The code goes into the APK Signing Block as one extra ID-value pair. The
 * v2/v3 signatures cover the APK's entries, central directory and end record,
 * not other pairs in that block, and Android ignores pairs it doesn't know. So
 * the copy installs exactly like the original and still takes updates signed
 * with the release key. The code is only a hint: it pre-fills signup, and the
 * server checks it like any code a person types.
 *
 * Pure JVM code (no Android APIs), tested in ApkReferralTest with Google's
 * own APK verifier.
 */
object ApkReferral {
    /** "FFRF" — our pair's ID in the APK Signing Block. */
    const val BLOCK_ID = 0x46465246

    /** apksigner's padding pair, which keeps the block a multiple of 4096 bytes. */
    private const val PADDING_ID = 0x42726577
    private const val PAGE = 4096
    private const val PAIR_HEADER = 12 // 8-byte length + 4-byte id

    private const val MAGIC_LO = 0x20676953204b5041L // "APK Sig "
    private const val MAGIC_HI = 0x3234206b636f6c42L // "Block 42"
    private const val EOCD_SIGNATURE = 0x06054b50
    private const val EOCD_SIZE = 22
    private const val MAX_COMMENT = 0xFFFF

    private val CODE = Regex("^[23456789ABCDEFGHJKMNPQRSTVWXYZ]{8}$")

    class NotSignedApkException(message: String) : Exception(message)

    fun isValidCode(code: String): Boolean = CODE.matches(code)

    /** The referral code carried by [apk], or null if there is none. */
    fun read(apk: File): String? = try {
        val layout = RandomAccessFile(apk, "r").use { parse(it) }
        layout.pairs.firstOrNull { it.id == BLOCK_ID }
            ?.value?.toString(Charsets.US_ASCII)
            ?.takeIf(::isValidCode)
    } catch (e: Exception) {
        null
    }

    /** Writes a copy of [source] to [target] carrying [code] (replacing any code it had). */
    fun embed(source: File, target: File, code: String) {
        require(isValidCode(code)) { "not a referral code" }
        RandomAccessFile(source, "r").use { input ->
            val layout = parse(input)
            val pairs = layout.pairs.filter { it.id != BLOCK_ID && it.id != PADDING_ID }.toMutableList()
            pairs += Entry(BLOCK_ID, code.toByteArray(Charsets.US_ASCII))
            if (layout.pairs.any { it.id == PADDING_ID }) {
                // Keep the block page-aligned, as apksigner made it.
                val unpadded = blockSize(pairs)
                var padding = (PAGE - unpadded % PAGE) % PAGE
                if (padding > 0 && padding < PAIR_HEADER) padding += PAGE
                if (padding > 0) pairs += Entry(PADDING_ID, ByteArray((padding - PAIR_HEADER).toInt()))
            }
            val block = encodeBlock(pairs)
            val eocd = ByteArray((input.length() - layout.eocdOffset).toInt())
            input.seek(layout.eocdOffset)
            input.readFully(eocd)
            ByteBuffer.wrap(eocd).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(16, (layout.blockOffset + block.size).toInt()) // new central directory offset

            target.parentFile?.mkdirs()
            RandomAccessFile(target, "rw").use { output ->
                output.setLength(0)
                val from = input.channel
                val to = output.channel
                copy(from, 0, layout.blockOffset, to)
                to.write(ByteBuffer.wrap(block))
                copy(from, layout.cdOffset, layout.eocdOffset - layout.cdOffset, to)
                to.write(ByteBuffer.wrap(eocd))
            }
        }
    }

    private class Entry(val id: Int, val value: ByteArray)

    private class Layout(val blockOffset: Long, val cdOffset: Long, val eocdOffset: Long, val pairs: List<Entry>)

    private fun parse(file: RandomAccessFile): Layout {
        val length = file.length()
        if (length < EOCD_SIZE) throw NotSignedApkException("too small to be a ZIP file")
        val tailSize = minOf(length, (EOCD_SIZE + MAX_COMMENT).toLong()).toInt()
        val tail = ByteArray(tailSize)
        file.seek(length - tailSize)
        file.readFully(tail)
        val buffer = ByteBuffer.wrap(tail).order(ByteOrder.LITTLE_ENDIAN)

        var eocdInTail = -1
        for (i in tailSize - EOCD_SIZE downTo 0) {
            if (buffer.getInt(i) == EOCD_SIGNATURE) {
                val commentLength = buffer.getShort(i + 20).toInt() and 0xFFFF
                if (i + EOCD_SIZE + commentLength == tailSize) {
                    eocdInTail = i
                    break
                }
            }
        }
        if (eocdInTail < 0) throw NotSignedApkException("no ZIP end record")
        val eocdOffset = length - tailSize + eocdInTail
        val cdSize = buffer.getInt(eocdInTail + 12).toLong() and 0xFFFFFFFFL
        val cdOffset = buffer.getInt(eocdInTail + 16).toLong() and 0xFFFFFFFFL
        if (cdOffset + cdSize != eocdOffset) throw NotSignedApkException("unexpected ZIP layout")
        if (cdOffset < 32) throw NotSignedApkException("no APK Signing Block")

        val footer = ByteBuffer.allocate(24).order(ByteOrder.LITTLE_ENDIAN)
        file.seek(cdOffset - 24)
        file.readFully(footer.array())
        val sizeInFooter = footer.getLong(0)
        if (footer.getLong(8) != MAGIC_LO || footer.getLong(16) != MAGIC_HI) {
            throw NotSignedApkException("no APK Signing Block")
        }
        val blockOffset = cdOffset - sizeInFooter - 8
        if (sizeInFooter < 24 || blockOffset < 0) throw NotSignedApkException("bad APK Signing Block size")

        val block = ByteBuffer.allocate((sizeInFooter + 8).toInt()).order(ByteOrder.LITTLE_ENDIAN)
        file.seek(blockOffset)
        file.readFully(block.array())
        if (block.getLong(0) != sizeInFooter) throw NotSignedApkException("APK Signing Block sizes differ")

        val pairs = mutableListOf<Entry>()
        var position = 8
        val end = block.capacity() - 24
        while (position < end) {
            if (end - position < 8) throw NotSignedApkException("truncated pair")
            val pairLength = block.getLong(position)
            if (pairLength < 4 || pairLength > end - position - 8) throw NotSignedApkException("bad pair length")
            val id = block.getInt(position + 8)
            val value = ByteArray((pairLength - 4).toInt())
            block.position(position + 12)
            block.get(value)
            pairs += Entry(id, value)
            position += 8 + pairLength.toInt()
        }
        return Layout(blockOffset, cdOffset, eocdOffset, pairs)
    }

    /** Whole block size: both size fields, the pairs and the magic. */
    private fun blockSize(pairs: List<Entry>): Long = 8L + pairs.sumOf { PAIR_HEADER.toLong() + it.value.size } + 8 + 16

    private fun encodeBlock(pairs: List<Entry>): ByteArray {
        val total = blockSize(pairs)
        val out = ByteBuffer.allocate(total.toInt()).order(ByteOrder.LITTLE_ENDIAN)
        out.putLong(total - 8)
        for (pair in pairs) {
            out.putLong(4L + pair.value.size)
            out.putInt(pair.id)
            out.put(pair.value)
        }
        out.putLong(total - 8)
        out.putLong(MAGIC_LO)
        out.putLong(MAGIC_HI)
        return out.array()
    }

    private fun copy(from: FileChannel, position: Long, count: Long, to: FileChannel) {
        var done = 0L
        while (done < count) {
            val moved = from.transferTo(position + done, count - done, to)
            if (moved <= 0) throw java.io.IOException("copy stalled")
            done += moved
        }
    }
}
