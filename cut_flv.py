import sys,os
import logging

from optparse import OptionParser

from constants import TAG_TYPE_AUDIO, TAG_TYPE_VIDEO, TAG_TYPE_SCRIPT
from constants import FRAME_TYPE_KEYFRAME
from constants import H264_PACKET_TYPE_SEQUENCE_HEADER
from constants import H264_PACKET_TYPE_NALU
from astypes import MalformedFLV, FLVObject
from tags import FLV, EndOfFile, AudioTag, VideoTag, ScriptTag

log = logging.getLogger('flvlib.cut-flv')

def get_next_unuse_name(absfilename):
    cur_file_path = os.path.dirname(os.path.realpath(absfilename))
    if cur_file_path.find('result') == -1:
        tar_file_path = cur_file_path + '\\result\\'
    else:
        tar_file_path = cur_file_path + '\\'
    if not os.path.exists(tar_file_path):
        os.mkdir(tar_file_path)    
    srcFileName, ext=os.path.splitext(absfilename) 
    srcFileName = srcFileName.split('\\')[-1]
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
            print('CuttingAudioTag ',parent.first_media_tag_offset)


class CuttingVideoTag(VideoTag):

    def parse(self):
        parent = self.parent_flv
        VideoTag.parse(self)

        parent.no_video = False

        if (not parent.first_media_tag_offset and
                self.h264_packet_type != H264_PACKET_TYPE_SEQUENCE_HEADER):
            parent.first_media_tag_offset = self.offset
            print('CuttingVideoTag ',parent.first_media_tag_offset)


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
            raise MalformedFLV("Invalid tag type: %d", tag_type)


def cut_file(inpath):
    print("Cutting file '%s'"%(inpath))

    try:
        f = open(inpath, 'rb')
    except IOError as e:
        print(e, inpath)

    file_name = get_next_unuse_name(inpath)
    try:
        fo = open(file_name, 'wb')
        print('new out file:', file_name)
    except IOError as e:
        print(e, file_name)

    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    count = 0
    header_tag = None
    thresholdOfKeyFrameCombine = 10
    countOfKeyFrameCombine = 1
    startTagTimeStamp = 0

    # get common header part
    try:
        while(True):
            tag = next(tag_iterator)
            count = count + 1
            if isinstance(tag, VideoTag) and tag.h264_packet_type == H264_PACKET_TYPE_SEQUENCE_HEADER:
                print('find header, count = ', count)
                header_tag = tag
                break
    except MalformedFLV as e:
        print(e)
    except EndOfFile:
        print("Unexpected end of file on file `%s' 1"%file_name)
    except StopIteration:
        pass

    try:
        while True:
            tag = next(tag_iterator)
            count = count + 1
            # some buggy software, like gstreamer's flvmux, puts a metadata tag
            # at the end of the file with timestamp 0, and we don't want to
            # base our duration computation on that
            if isinstance(tag, VideoTag) and tag.frame_type == FRAME_TYPE_KEYFRAME:
                if countOfKeyFrameCombine > thresholdOfKeyFrameCombine:
                    countOfKeyFrameCombine = 1
                    fo.close()
                    file_name = get_next_unuse_name(file_name)
                    try:
                        fo = open(file_name, 'wb')
                        print('new out file:', file_name)
                    except IOError as e:
                        print(e, file_name)

                if countOfKeyFrameCombine == 1:
                    print('start new frame')
                    startTagTimeStamp = tag.timestamp
                    # write common part
                    oldOffset = f.tell()
                    f.seek(0)
                    fo.write(f.read(header_tag.endOffset))
                    f.seek(oldOffset)
                countOfKeyFrameCombine = countOfKeyFrameCombine + 1

            try:
                fo.write(tag.getWholeTagWithTimeOffset(startTagTimeStamp))
            except EndOfFile:
                print("Unexpected end of file on file `%s' 2" % file_name)

    except MalformedFLV as e:
        print(e)
    except EndOfFile as e:
        print(e)
    except StopIteration as e:
        print(e)
        pass

    f.close()
    fo.close()
    return True

def cut_to_new_file(src_f, tar_file_name, action, last_tag, tag_after_last_tag, first_keyframe_after_start):
    print('enter cut_to_new_file')
    try:
        fo = open(tar_file_name, 'wb')
    except IOError as xxx_todo_changeme1:
        (errno, strerror) = xxx_todo_changeme1.args
        print("Failed to open `%s': %s"%(tar_file_name, strerror))
        return False
    
    if not first_media_tag_offset:
        print("The file `%s' does not have any media content"%tar_file_name)
        return False

    if not last_tag:
        log.error("The file `%s' does not have any content with a non-zero timestamp"%tar_file_name)
        return False

    if not first_keyframe_after_start:
        log.error("The file `%s' has no keyframes greater than start time"%tar_file_name)
        return False

    print("Creating the output file ", tar_file_name)

    print("First tag to output %s"%first_keyframe_after_start)
    print("Last tag to output %s"%last_tag)
    print("Tag after last tag %s"%tag_after_last_tag)

    src_f.seek(0)
    print("copying up to %d bytes"%first_media_tag_offset)
    fo.write(src_f.read(first_media_tag_offset))
    print("seeking to %d bytes"%first_keyframe_after_start.offset)
    if tag_after_last_tag:
        end_offset = tag_after_last_tag.offset
    else:
        src_f.seek(0, 2)
        end_offset = src_f.tell()
    print("end offset %d"%end_offset)
    src_f.seek(first_keyframe_after_start.offset)

    copy_bytes = end_offset - first_keyframe_after_start.offset
    print("copying %d bytes"%copy_bytes)
    fo.write(src_f.read(copy_bytes))
    fo.close()

def process_options():
    usage = "%prog file outfile"
    description = ("Cut out part of a FLV file. Start and end times are "
                   "timestamps that will be compared to the timestamps "
                   "of tags from inside the file. Tags from outside of the "
                   "start/end range will be discarded, taking care to always "
                   "start the new file with a keyframe. "
                   "The script accepts one input and one output file path.")
    version = "%%prog flvlib %s" % __versionstr__
    parser = OptionParser(usage=usage, description=description,
                          version=version)
    parser.add_option("-s", "--start-time", help="start time to cut from")
    parser.add_option("-e", "--end-time", help="end time to cut to")
    parser.add_option("-v", "--verbose", action="count",
                      default=0, dest="verbosity",
                      help="be more verbose, each -v increases verbosity")
    options, args = parser.parse_args(sys.argv)

    if len(args) < 2:
        parser.error("You have to provide an input and output file path")

    if not options.start_time and not options.end_time:
        parser.error("You need to provide at least "
                     "one of start time or end time ")

    if options.verbosity > 3:
        options.verbosity = 3

    log.setLevel({0: logging.ERROR, 1: logging.WARNING,
                  2: logging.INFO, 3: logging.DEBUG}[options.verbosity])

    return options, args


def cut_files():
    options, args = process_options()
    return cut_file(args[1], args[2], options.start_time, options.end_time)


def main():
    try:
        outcome = cut_files()
    except KeyboardInterrupt:
        # give the right exit status, 128 + signal number
        # signal.SIGINT = 2
        sys.exit(128 + 2)
    except EnvironmentError as xxx_todo_changeme2:
        (errno, strerror) = xxx_todo_changeme2.args
        try:
            print(strerror, file=sys.stderr)
        except Exception:
            pass
        sys.exit(2)

    if outcome:
        sys.exit(0)
    else:
        sys.exit(1)

def make_flv_complete(file_name):
    print('make flv complete')
    try:
        f = open(file_name, 'rb')
    except IOError as xxx_todo_changeme:
        (errno, strerror) = xxx_todo_changeme.args
        print("Failed to open `%s': %s"%(inpath, strerror))
        return False

    srcFileName, ext = os.path.splitext(file_name) 
    tarFileName = srcFileName + 'temp' + ext
    print('create temp file %s'%tarFileName)
    
    try:
        fo = open(tarFileName, 'wb')
    except IOError as xxx_todo_changeme1:
        (errno, strerror) = xxx_todo_changeme1.args
        print("Failed to open `%s': %s"%(tar_file_name, strerror))
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
                    # print('f.tell()=%d'%(f.tell()))
                    # print('fo.tell()=%d' % (fo.tell()))
                except EndOfFile:
                    print("Unexpected end of file on file `%s' 2"%file_name)
                finally:
                    break
            count = count + 1

    except MalformedFLV as e:
        print(e)
    except EndOfFile:
        print("Unexpected end of file on file `%s' 1"%file_name)

    except StopIteration:
        pass

    try:
        while True:
            tag = next(tag_iterator)
            if count > 720:
                if startTagTimeStamp == 0:
                    startTagTimeStamp = tag.timestamp
                    print('startTagTimeStamp=%d'%(startTagTimeStamp))
                try:
                    # print('original tag : ', tag.printWholeTag())
                    fo.write(tag.getWholeTagWithTimeOffset(startTagTimeStamp))
                except EndOfFile:
                    print("Unexpected end of file on file `%s' 2"%file_name)
            count = count + 1
    except MalformedFLV as e:
        print(e)
    except EndOfFile:
        print("Unexpected end of file on file `%s' 1"%file_name)

    except StopIteration:
        pass

    f.close()
    fo.close()
    
    print('make_flv_complete done, count =', count)
    
    return True

def make_timestamp_start_0(file_name):
    print('make_timestamp_start_0 enter')
    try:
        f = open(file_name, 'rb')
    except IOError as xxx_todo_changeme:
        (errno, strerror) = xxx_todo_changeme.args
        print("Failed to open `%s': %s" % (inpath, strerror))
        return False

    srcFileName, ext = os.path.splitext(file_name)
    tarFileName = srcFileName + 'temp' + ext
    print('create temp file %s' % tarFileName)

    try:
        fo = open(tarFileName, 'wb')
    except IOError as xxx_todo_changeme1:
        (errno, strerror) = xxx_todo_changeme1.args
        print("Failed to open `%s': %s" % (tar_file_name, strerror))
        return False
    
    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    last_tag= None
    timeStampOffset = None
    count = 0
    copy_bytes = 0
    f.seek(0)
    '''
    tag = next(tag_iterator)
    if isinstance(tag, ScriptTag):
        try:
            fo.write(f.read(tag.offset + tag.size))
            f.seek(tag.offset + tag.size)
        except EndOfFile:
            print("Unexpected end of file on file `%s' 2"%file_name)  
    '''
    try:
        while True:
            tag = next(tag_iterator)
            last_tag = tag
            if isinstance(tag, VideoTag):
                print('VideoTag,', tag.__repr__(),' ',count)
            elif isinstance(tag, AudioTag):
                print('AudioTag,', tag.__repr__(),' ',count)
            elif isinstance(tag, ScriptTag):
                print('ScriptTag,', count)
                test_offset = tag.offset
                print('test_offset', test_offset)
            elif isinstance(tag, ScriptAMF3Tag):
                print('ScriptAMF3Tag,', count)
            else:
                print('unknow tag,',count)
            print('tag.timestamp=%d'%(tag.timestamp))
            count = count + 1
    except MalformedFLV as e:
        print("MalformedFLV, ", e)
    except EndOfFile:
        print("EndOfFile")
        
    except StopIteration:

        pass

    try:
        f.seek(0)
        fo.write(f.read(last_tag.offset))
    except EndOfFile:
        print("Unexpected end of file on file `%s' 2"%file_name)   
    f.close()
    fo.close()
    
    print('make_flv_complete done, count =', count)
    
    return True


def print_flv(file_name):
    print('print_flv enter')
    try:
        f = open(file_name, 'rb')
    except IOError as xxx_todo_changeme:
        (errno, strerror) = xxx_todo_changeme.args
        print("Failed to open `%s': %s" % (inpath, strerror))
        return False

    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    count = 0
    f.seek(0)

    try:
        while True:
            tag = next(tag_iterator)
            if isinstance(tag, VideoTag):
                print('VideoTag,', tag.__repr__(), ' ', count)
            elif isinstance(tag, AudioTag):
                print('AudioTag,', tag.__repr__(), ' ', count)
            elif isinstance(tag, ScriptTag):
                print('ScriptTag,', count)
                test_offset = tag.offset
                print('test_offset', test_offset)
            elif isinstance(tag, ScriptAMF3Tag):
                print('ScriptAMF3Tag,', count)
            else:
                print('unknow tag,', count)
            print('tag.timestamp=%d' % (tag.timestamp))
            count = count + 1
    except MalformedFLV as e:
        print("MalformedFLV, ", e)
    except EndOfFile:
        print("EndOfFile")

    except StopIteration:

        pass

    f.close()

    print('print_flv done, count =', count)

    return True


if __name__ == '__main__':
    #main()
    log.setLevel({0: logging.ERROR, 1: logging.WARNING,
              2: logging.INFO, 3: logging.DEBUG}[3])
    #cut_file('D:\\test\\1\\123.flv', 0, 1000000)
    #make_flv_complete('D:\\test\\1\\123.flv')
    cut_file('D:\\MY_DownLoad\\11111\\cut\\06cface5632f2f483868bf7e5c20171119周日152859.05.flv')
    # make_flv_complete('D:\\MY_DownLoad\\11111\\cut\\ff87cc9c283636af2de84ff20171214周四210542.55.flv')
    # print_flv('D:\\MY_DownLoad\\11111\\cut\\5dd649b8539000b1b320171106周一235929.38.flv')
    # make_timestamp_start_0('D:\\MY_DownLoad\\11111\\cut\\ff87cc9c283636af2de84ff20171214周四210542.55.flv')
    #cut_file('D:\\MY_DownLoad\\11111\\cut\\ff87cc9c283636af2de84ff20171214周四210542.55.flv', 0, 20000)
