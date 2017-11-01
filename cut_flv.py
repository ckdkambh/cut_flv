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
    srcFileName, ext=os.path.splitext(absfilename)
    cut_index = srcFileName.find('_cut')
    if cut_index != -1:
        cur_num_str = srcFileName[cut_index + 4:]
        cur_num = int(cur_num_str)
        next_num = cur_num + 1
        next_num_str = str(next_num).zfill(3)
        return srcFileName[:cut_index + 4]+next_num_str+ext
    else:
        return srcFileName+'_cut001'+ext

class CuttingAudioTag(AudioTag):

    def parse(self):
        parent = self.parent_flv
        AudioTag.parse(self)

        if not parent.first_media_tag_offset:
            parent.first_media_tag_offset = self.offset


class CuttingVideoTag(VideoTag):

    def parse(self):
        parent = self.parent_flv
        VideoTag.parse(self)

        parent.no_video = False

        if (not parent.first_media_tag_offset and
                self.h264_packet_type != H264_PACKET_TYPE_SEQUENCE_HEADER):
            parent.first_media_tag_offset = self.offset


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


def cut_file(inpath, start_time, interval_time):
    print("Cutting file '%s' interval_time=%s"%(inpath, interval_time))

    try:
        f = open(inpath, 'rb')
    except IOError as xxx_todo_changeme:
        (errno, strerror) = xxx_todo_changeme.args
        log.error("Failed to open `%s': %s", inpath, strerror)
        return False

    if start_time is None:
        start_time = 0
    else:
        start_time = int(start_time)
        
    if interval_time is None:
        end_time = -1
    else:
        end_time = start_time + int(interval_time)

    print('start_time :', start_time, ', end_time :', end_time)
    
    flv = CuttingFLV(f)
    tag_iterator = flv.iter_tags()
    last_tag = None
    tag_after_last_tag = None
    first_keyframe_after_start = None
    file_name = get_next_unuse_name(inpath)
    print('first_file_name:',file_name)
    
    try:
        while True:
            tag = next(tag_iterator)
            # some buggy software, like gstreamer's flvmux, puts a metadata tag
            # at the end of the file with timestamp 0, and we don't want to
            # base our duration computation on that
            if tag.timestamp != 0 and (
                    tag.timestamp <= end_time or end_time == -1):
                last_tag = tag #find last tag match the end_time
            elif tag_after_last_tag is None and tag.timestamp != 0:
                tag_after_last_tag = tag #find tag after last tag match the end_time
                cut_to_new_file(f, file_name, flv.first_media_tag_offset, last_tag, tag_after_last_tag, first_keyframe_after_start)
                file_name = get_next_unuse_name(file_name)
                start_time = start_time + int(interval_time)
                end_time = start_time + int(interval_time)
                last_tag = None
                tag_after_last_tag = None
                first_keyframe_after_start = None
                
            if not first_keyframe_after_start and tag.timestamp > start_time:
                if isinstance(tag, VideoTag):
                    if (tag.frame_type == FRAME_TYPE_KEYFRAME and
                            tag.h264_packet_type == H264_PACKET_TYPE_NALU):
                        first_keyframe_after_start = tag
                elif flv.no_video:
                    first_keyframe_after_start = tag
    except MalformedFLV as e:
        message = e[0] % e[1:]
        log.error("The file `%s' is not a valid FLV file: %s", inpath, message)
        return False
    except EndOfFile:
        log.error("Unexpected end of file on file `%s'", inpath)
        return False
    except StopIteration:
        cut_to_new_file(f, file_name, flv.first_media_tag_offset, last_tag, tag_after_last_tag, first_keyframe_after_start)
        pass

    f.close()
    return True

def cut_to_new_file(src_f, tar_file_name, first_media_tag_offset, last_tag, tag_after_last_tag, first_keyframe_after_start):
    try:
        fo = open(tar_file_name, 'wb')
    except IOError as xxx_todo_changeme1:
        (errno, strerror) = xxx_todo_changeme1.args
        print("Failed to open `%s': %s"%(tar_file_name, strerror))
        return False
    
    if not first_media_tag_offset:
        print("The file `%s' does not have any media content"%inpath)
        return False

    if not last_tag:
        log.error("The file `%s' does not have any content with a "
                  "non-zero timestamp", inpath)
        return False

    if not first_keyframe_after_start:
        log.error("The file `%s' has no keyframes greater than start time %d",
                  inpath, start_time)
        return False

    print("Creating the output file")

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


if __name__ == '__main__':
    #main()
    log.setLevel({0: logging.ERROR, 1: logging.WARNING,
              2: logging.INFO, 3: logging.DEBUG}[3])
    cut_file('D:\\test\\1\\123.flv', 0, 60000)
