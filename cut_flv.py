import sys,os
import logging
import logging.handlers

from optparse import OptionParser

from constants import TAG_TYPE_AUDIO, TAG_TYPE_VIDEO, TAG_TYPE_SCRIPT
from constants import FRAME_TYPE_KEYFRAME
from constants import H264_PACKET_TYPE_SEQUENCE_HEADER
from constants import H264_PACKET_TYPE_NALU
from astypes import MalformedFLV, FLVObject
from tags import FLV, EndOfFile, AudioTag, VideoTag, ScriptTag

log = logging.getLogger('flvlib.cut-flv')
logger = logging.getLogger('cut_flv')

def get_next_unuse_name(absfilename):
    cur_file_path = os.path.dirname(os.path.realpath(absfilename))
    srcFileName, ext = os.path.splitext(absfilename)
    srcFileName = srcFileName.split('\\')[-1]

    if cur_file_path.find('result') == -1:
        tar_file_path = cur_file_path + '\\result\\'
    else:
        tar_file_path = cur_file_path + '\\'

    if not os.path.exists(tar_file_path):
        os.mkdir(tar_file_path)
    cut_index = srcFileName.find('_cut')
    if cut_index != -1:
        cur_num_str = srcFileName[cut_index + 4:]
        cur_num = int(cur_num_str)
        next_num = cur_num + 1
        next_num_str = str(next_num).zfill(3)
        return tar_file_path + srcFileName[:cut_index + 4]+next_num_str+ext
    else:
        return tar_file_path + srcFileName+'_cut001'+ext

class CuttingAudioTag(AudioTag):

    def parse(self):
        parent = self.parent_flv
        AudioTag.parse(self)

        if not parent.first_media_tag_offset:
            parent.first_media_tag_offset = self.offset
            logger.info('CuttingAudioTag %d',parent.first_media_tag_offset)


class CuttingVideoTag(VideoTag):

    def parse(self):
        parent = self.parent_flv
        VideoTag.parse(self)

        parent.no_video = False

        if (not parent.first_media_tag_offset and
                self.h264_packet_type != H264_PACKET_TYPE_SEQUENCE_HEADER):
            parent.first_media_tag_offset = self.offset
            logger.info('CuttingVideoTag %d',parent.first_media_tag_offset)


tag_to_class = {
    TAG_TYPE_AUDIO: CuttingAudioTag,
    TAG_TYPE_VIDEO: CuttingVideoTag,
    TAG_TYPE_SCRIPT: ScriptTag
}


class CuttingFLV(FLV):

    def __init__(self, f):
        FLV.__init__(self, f)
        self.metadata = None
        self.keyframes = FLVObject()
        self.keyframes.filepositions = []
        self.keyframes.times = []
        self.no_video = True
        self.audio_tag_number = 0
        self.first_media_tag_offset = None

    def tag_type_to_class(self, tag_type):
        try:
            return tag_to_class[tag_type]
        except KeyError:
            logger.error('Invalid tag type: %d', tag_type)
            return None


def cut_file(inpath, flvFileObj):
    logger.info("Cutting file %s"%(inpath))

    try:
        f = open(inpath, 'rb')
    except IOError as e:
        logger.error(e, inpath)

    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    count = 0
    sizeThresholdOfKeyFrameCombine = 16000000

    if not flvFileObj:
        flvFileObj = {}

        file_name = get_next_unuse_name(inpath)
        flvFileObj['file_name'] = file_name
        try:
            fo = open(file_name, 'wb')
            logger.info('new out file:%s', file_name)
        except IOError as e:
            logger.error(e, file_name)
        flvFileObj['fo'] = fo

        sizeCountOfKeyFrameCombine = -1
        startTagTimeStamp = 0

        header_tag = None
        # get common header part
        try:
            while(True):
                tag = next(tag_iterator)
                if tag == None:
                    continue
                count = count + 1
                if isinstance(tag, VideoTag) and tag.h264_packet_type == H264_PACKET_TYPE_SEQUENCE_HEADER:
                    logger.info('find header, count=%d', count)
                    header_tag = tag
                    break
        except MalformedFLV as e:
            logger.error(e)
        except EndOfFile:
            logger.error("Unexpected end of file on file %s 1"%file_name)
        except StopIteration:
            pass

        flvFileObj['header_tag'] = header_tag
    else:
        fo = flvFileObj['fo']
        sizeCountOfKeyFrameCombine = flvFileObj['sizeCountOfKeyFrameCombine']
        startTagTimeStamp = flvFileObj['startTagTimeStamp']
        header_tag = flvFileObj['header_tag']
        file_name = flvFileObj['file_name']

    try:
        while True:
            tag = next(tag_iterator)
            if tag == None:
                continue
            count = count + 1
            logger.debug('sizeCountOfKeyFrameCombine:%d, sizeThresholdOfKeyFrameCombine:%d', sizeCountOfKeyFrameCombine, sizeThresholdOfKeyFrameCombine)
            # some buggy software, like gstreamer's flvmux, puts a metadata tag
            # at the end of the file with timestamp 0, and we don't want to
            # base our duration computation on that
            if isinstance(tag, VideoTag) and tag.frame_type == FRAME_TYPE_KEYFRAME:
                if sizeCountOfKeyFrameCombine == -1:
                    sizeCountOfKeyFrameCombine = 0
                if sizeCountOfKeyFrameCombine > sizeThresholdOfKeyFrameCombine:
                    flvFileObj = None
                    sizeCountOfKeyFrameCombine = 0
                    fo.close()
                    file_name = get_next_unuse_name(file_name)
                    try:
                        fo = open(file_name, 'wb')
                        logger.info('new out file:%s', file_name)
                    except IOError as e:
                        logger.error(e, file_name)

                if sizeCountOfKeyFrameCombine == 0:
                    logger.info('start new frame,%s',file_name)
                    startTagTimeStamp = tag.timestamp
                    # write common part
                    oldOffset = f.tell()
                    f.seek(0)
                    fo.seek(0)
                    test = f.read(header_tag.endOffset)
                    fo.write(test)
                    logger.debug('file_name:%s, test:%s', file_name, test)
                    f.seek(oldOffset)
                    sizeCountOfKeyFrameCombine = sizeCountOfKeyFrameCombine + header_tag.endOffset
            if sizeCountOfKeyFrameCombine >= 0:
                try:
                    fo.write(tag.getWholeTagWithTimeOffset(startTagTimeStamp))
                    sizeCountOfKeyFrameCombine = sizeCountOfKeyFrameCombine + tag.size
                    # logger.info('sizeCountOfKeyFrameCombine=%d',sizeCountOfKeyFrameCombine)
                except EndOfFile:
                    logger.error("Unexpected end of file on file `%s' 2" % file_name)

    except MalformedFLV as e:
        logger.error(e)
    except EndOfFile as e:
        logger.error(e)
    except StopIteration as e:
        logger.error(e)
        pass

    f.close()
    if not flvFileObj:
        fo.close()
    else:
        flvFileObj['sizeCountOfKeyFrameCombine'] = sizeCountOfKeyFrameCombine
        flvFileObj['startTagTimeStamp'] = startTagTimeStamp
    return flvFileObj

def make_flv_complete(file_name):
    logger.info('make flv complete')
    try:
        f = open(file_name, 'rb')
    except IOError as e:
        logger.error(e)
        return False

    srcFileName, ext = os.path.splitext(file_name)
    tarFileName = srcFileName + 'temp' + ext
    logger.info('create temp file %s'%tarFileName)

    try:
        fo = open(tarFileName, 'wb')
    except IOError as e:
        logger.error(e)
        return False

    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    count = 0
    startTagTimeStamp = 0

    try:
        while(True):
            tag = next(tag_iterator)
            if isinstance(tag, VideoTag) and tag.h264_packet_type == H264_PACKET_TYPE_SEQUENCE_HEADER:
                try:
                    oldOffset = f.tell()
                    f.seek(0)
                    fo.write(f.read(tag.endOffset))
                    f.seek(oldOffset)
                    logger.debug('f.tell()=%d'%(f.tell()))
                    logger.debug('fo.tell()=%d'%(fo.tell()))
                except EndOfFile:
                    logger.error("Unexpected end of file on file `%s' 2"%file_name)
                finally:
                    break
            count = count + 1

    except MalformedFLV as e:
        logger.error(e)
    except EndOfFile:
        logger.error("Unexpected end of file on file `%s' 1"%file_name)

    except StopIteration:
        pass

    try:
        while True:
            tag = next(tag_iterator)
            if count > 720:
                if startTagTimeStamp == 0:
                    startTagTimeStamp = tag.timestamp
                    logger.info('startTagTimeStamp=%d'%(startTagTimeStamp))
                try:
                    logger.debug('original tag:%d', tag.printWholeTag())
                    fo.write(tag.getWholeTagWithTimeOffset(startTagTimeStamp))
                except EndOfFile:
                    logger.error("Unexpected end of file on file %s 2"%file_name)
            count = count + 1
    except MalformedFLV as e:
        logger.error(e)
    except EndOfFile:
        logger.error("Unexpected end of file on file %s 1"%file_name)

    except StopIteration:
        pass

    f.close()
    fo.close()

    logger.info('make_flv_complete done, count=%d', count)

    return True

def make_timestamp_start_0(file_name):
    logger.info('make_timestamp_start_0 enter')
    try:
        f = open(file_name, 'rb')
    except IOError as e:
        logger.error(e)
        return False

    srcFileName, ext = os.path.splitext(file_name)
    tarFileName = srcFileName + 'temp' + ext
    logger.info('create temp file %s' % tarFileName)

    try:
        fo = open(tarFileName, 'wb')
    except IOError as e:
        logger.error(e)
        return False

    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    last_tag= None
    timeStampOffset = None
    count = 0
    copy_bytes = 0
    f.seek(0)

    try:
        while True:
            tag = next(tag_iterator)
            last_tag = tag
            if isinstance(tag, VideoTag):
                logger.info('VideoTag,%s,%d', tag.__repr__(), count)
            elif isinstance(tag, AudioTag):
                logger.info('AudioTag,%s,%d', tag.__repr__(), count)
            elif isinstance(tag, ScriptTag):
                logger.info('ScriptTag,%d', count)
                test_offset = tag.offset
                logger.info('test_offset=%d', test_offset)
            elif isinstance(tag, ScriptAMF3Tag):
                logger.info('ScriptAMF3Tag,%d', count)
            else:
                logger.info('unknow tag,%d',count)
            logger.info('tag.timestamp=%d'%(tag.timestamp))
            count = count + 1
    except MalformedFLV as e:
        logger.error(e)
    except EndOfFile:
        logger.error("EndOfFile")

    except StopIteration:

        pass

    try:
        f.seek(0)
        fo.write(f.read(last_tag.offset))
    except EndOfFile:
        logger.error("Unexpected end of file on file `%s' 2"%file_name)
    f.close()
    fo.close()

    logger.info('make_flv_complete done, count=%d', count)

    return True


def print_flv(file_name):
    logger.info('print_flv enter')
    try:
        f = open(file_name, 'rb')
    except IOError as e:
        logger.error(e)
        return False

    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    count = 0
    f.seek(0)

    try:
        while True:
            tag = next(tag_iterator)
            if tag == None:
                continue
            if isinstance(tag, VideoTag):
                logger.info('VideoTag, %s, %s', tag.__repr__(), count)
            elif isinstance(tag, AudioTag):
                logger.info('AudioTag, %s, %s', tag.__repr__(), count)
            elif isinstance(tag, ScriptTag):
                logger.info('ScriptTag, count=%d', count)
                test_offset = tag.offset
                logger.info('test_offset=%d', test_offset)
            elif isinstance(tag, ScriptAMF3Tag):
                logger.info('ScriptAMF3Tag, count=%d', count)
            else:
                logger.info('unknow tag, count=%d', count)
            logger.info('tag.timestamp=%d' % (tag.timestamp))
            count = count + 1
    except MalformedFLV as e:
        logger.error(e)
    except EndOfFile:
        logger.error("EndOfFile")

    except StopIteration:

        pass

    f.close()

    logger.info('print_flv done, count=%d', count)

    return True

def getAllFlvFile(inPath):
    fileList = os.listdir(inPath)
    out = []
    for i in fileList:
        path = os.path.join(inPath, i)
        if i.endswith('flv') and os.path.isfile(path):
            out.append(path)
    return out

if __name__ == '__main__':
    LOG_FILE = 'D:\\gitCode\\log_data\\cut_flv.log'
    handler = logging.handlers.RotatingFileHandler(LOG_FILE, mode='w')  # 实例化handler
    fmt = '%(asctime)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s'

    formatter = logging.Formatter(fmt)  # 实例化formatter
    handler.setFormatter(formatter)  # 为handler添加formatter

    logger = logging.getLogger('cut_flv')  # 获取名为tst的logger
    logger.addHandler(handler)  # 为logger添加handler
    ch = logging.StreamHandler()
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)

    logger.info('############start cut_flv program####################')
    List = getAllFlvFile('D:\\MY_DownLoad\\11111\\cut\\')
    fileObj = None
    for i in List:
        fileObj = cut_file(i, fileObj)
    #cut_file('D:\\test\\1\\123.flv', 0, 1000000)
    #make_flv_complete('D:\\test\\1\\123.flv')
    # cut_file('D:\\MY_DownLoad\\11111\\cut\\3f04895cb8790520171008周日131210.29.flv.flv')
    # make_flv_complete('D:\\MY_DownLoad\\11111\\cut\\ff87cc9c283636af2de84ff20171214周四210542.55.flv')
    # print_flv('D:\\MY_DownLoad\\11111\\cut\\4c0a5e8f572ff422e80393f5606d0a1d.flv')
    # make_timestamp_start_0('D:\\MY_DownLoad\\11111\\cut\\ff87cc9c283636af2de84ff20171214周四210542.55.flv')
    #cut_file('D:\\MY_DownLoad\\11111\\cut\\ff87cc9c283636af2de84ff20171214周四210542.55.flv', 0, 20000)
