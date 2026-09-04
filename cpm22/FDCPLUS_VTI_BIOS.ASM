;=============================================================================
; IMSAI old-school CP/M 2.2 BIOS - FDC+ Drive Type 8 + Polymorphic VTI
;
; Target hardware:
;   North Star ZPB-A2 Z80 CPU
;   Altair FDC+ firmware 1.8, Drive Type 8 / iCOM FD3712 at 08H/09H
;   Shugart SA-800-class IBM-3740 8-inch SSSD drive(s)
;   Polymorphic VTI framebuffer FC00H-FFFFH, keyboard port FCH
;   VTI JMP2 -> S-100 VI2 -> ZPB RST 2 -> page-zero 0010H
;   No monitor ROM, no PIC-8, no CF/IDE
;
; CP/M layout is generated with MOVCPM 62 * from Mike Douglas's supplied
; CPM22v1.0-FDC+3712-48K image:
;   CCP  DE00H
;   BDOS E600H
;   BIOS F400H-F77FH (standard 896-byte BIOS reservation)
;
; The physical machine still has 63K ordinary RAM from 0000H-FBFFH. CP/M is
; deliberately sized as 62K so the otherwise-unused F780H-FBFFH region can be
; used as BIOS runtime workspace while the on-disk BIOS remains within the
; standard 51 system sectors. This source assembles to 784 bytes.
;
; The FDC+ low-level command sequence is derived from the physically-proven
; native FDC3712 module in peclark1/s100-target-system-4k-master-rom.
;=============================================================================

CCP     EQU 0DE00H
BDOS    EQU 0E600H
BIOS    EQU 0F400H
VTI     EQU 0FC00H
KPORT   EQU 0FCH

IOBYTE  EQU 0003H
CDISK   EQU 0004H

; Runtime work RAM -- intentionally outside the 51-sector CP/M system image.
DIRBUF  EQU 0F780H
CSV0    EQU 0F800H
ALV0    EQU 0F810H
CSV1    EQU 0F830H
ALV1    EQU 0F840H
KEYBUF  EQU 0F860H
KHEAD   EQU 0F870H
KTAIL   EQU 0F871H
CURPTR  EQU 0F872H
CURDRV  EQU 0F874H
CURTRK  EQU 0F875H
CURSEC  EQU 0F876H
DMAADR  EQU 0F877H
DRVTRK  EQU 0F879H
STACK   EQU 0FBF0H

CMDOUT  EQU 08H
DATAIN  EQU 08H
DATAOUT EQU 09H

C_READ      EQU 03H
C_WRITE     EQU 05H
C_SEEK      EQU 09H
C_CLRERR    EQU 0BH
C_RESTORE   EQU 0DH
C_SETTRK    EQU 11H
C_LDCFG     EQU 15H
C_DRVSEC    EQU 21H
C_WRTBUF    EQU 31H
C_RDBUF     EQU 40H
C_SHIFT     EQU 41H
C_RESET     EQU 81H

S_BUSY      EQU 01H
S_CRCERR    EQU 08H
S_WRTPRT    EQU 10H
S_NOTRDY    EQU 20H

        ORG BIOS
        JMP BOOT
        JMP WBOOT
        JMP CONST
        JMP CONIN
        JMP CONOUT
        JMP CONOUT
        JMP CONOUT
        JMP CONIN
        JMP HOME
        JMP SELDSK
        JMP SETTRK
        JMP SETSEC
        JMP SETDMA
        JMP READ
        JMP WRITE
        JMP LISTST
        JMP SECTRAN

BOOT:
        DI
        LXI SP,STACK
        CALL VTICLEAR
        CALL FDCINIT
        XRA A
        STA CDISK
        JMP GOCPM

WBOOT:
        DI
        LXI SP,STACK
        CALL FDCINIT

        XRA A
        STA CURDRV
        STA CURTRK
        MVI A,02H
        STA CURSEC
        LXI H,CCP
        SHLD DMAADR
        MVI B,25
        CALL LOADSEQ
        ORA A
        JNZ WBOOT

        MVI A,01H
        STA CURTRK
        STA CURSEC
        MVI B,19
        CALL LOADSEQ
        ORA A
        JNZ WBOOT
        JMP GOCPM

; Load consecutive physical sectors. Warm boot reloads only CCP+BDOS:
; T0 S2-S26 (25 sectors), then T1 S1-S19 (19 sectors).
LOADSEQ:
        PUSH B
        CALL READ
        POP B
        ORA A
        RNZ
        LDA CURSEC
        INR A
        STA CURSEC
        LHLD DMAADR
        LXI D,0080H
        DAD D
        SHLD DMAADR
        DCR B
        JNZ LOADSEQ
        XRA A
        RET

GOCPM:
        MVI A,0C3H
        STA 0000H
        LXI H,WBOOT
        SHLD 0001H
        STA 0005H
        LXI H,BDOS+6
        SHLD 0006H

        ; ZPB interrupt acknowledge for VI2 supplies RST 2 -> 0010H.
        STA 0010H
        LXI H,KBDISR
        SHLD 0011H

        XRA A
        STA KHEAD
        STA KTAIL
        EI
        LDA CDISK
        MOV C,A
        JMP CCP

;=============================================================================
; Polymorphic VTI console
;=============================================================================
; Factory-assembled VTI cards do not provide the optional keyboard status port,
; so keyboard readiness is maintained by an interrupt-fed 16-byte ring buffer.

CONST:
        LDA KHEAD
        MOV B,A
        LDA KTAIL
        CMP B
        MVI A,00H
        RZ
        DCR A                   ; FFH = character ready
        RET

CONIN:
        EI
CINWAIT:
        LDA KHEAD
        MOV B,A
        LDA KTAIL
        CMP B
        JNZ CINGET
        HLT                     ; wake on VTI VI2 interrupt
        JMP CINWAIT
CINGET:
        DI
        MOV E,A
        INR A
        ANI 0FH
        STA KTAIL
        MVI D,00H
        LXI H,KEYBUF
        DAD D
        MOV A,M
        ANI 7FH
        EI
        RET

KBDISR:
        PUSH PSW
        PUSH B
        PUSH D
        PUSH H
        IN KPORT                ; reading VTI keyboard latch services keypress
        ANI 7FH
        MOV B,A
        LDA KHEAD
        MOV C,A                 ; C = old head
        INR A
        ANI 0FH
        MOV D,A                 ; D = next head
        LDA KTAIL
        CMP D
        JZ KFULL                ; full: drop newest byte
        MOV A,D
        STA KHEAD
        MVI D,00H
        MOV E,C
        LXI H,KEYBUF
        DAD D
        MOV M,B
KFULL:
        POP H
        POP D
        POP B
        POP PSW
        EI
        RET

VTICLEAR:
        LXI H,VTI
        LXI B,0400H
        MVI D,0A0H              ; ASCII space OR 80H = VTI character mode
VCLP:
        MOV M,D
        INX H
        DCX B
        MOV A,B
        ORA C
        JNZ VCLP
        LXI H,VTI
        SHLD CURPTR
        RET

CONOUT:
        MOV A,C
        CPI 0DH
        JZ VCR
        CPI 0AH
        JZ VLF
        CPI 08H
        JZ VBS
        CPI 20H
        RC
        ORI 80H                 ; VTI bit 7 selects alphanumeric character mode
        LHLD CURPTR
        MOV M,A
        INX H
        MOV A,H
        ORA L                    ; FFFFH + 1 wraps to 0000H
        JZ VSCROLL
        SHLD CURPTR
        RET
VCR:
        LHLD CURPTR
        MOV A,L
        ANI 0C0H                ; 64-column line start
        MOV L,A
        SHLD CURPTR
        RET
VLF:
        LHLD CURPTR
        LXI D,0040H
        DAD D
        MOV A,H
        CPI 0FCH
        JC VSCROLL
        SHLD CURPTR
        RET
VBS:
        LHLD CURPTR
        MOV A,H
        CPI 0FCH
        JNZ VBSDEC
        MOV A,L
        ORA A
        RZ
VBSDEC:
        DCX H
        SHLD CURPTR
        RET

VSCROLL:
        LXI H,0FC40H
        LXI D,0FC00H
        LXI B,03C0H              ; copy rows 1-15 to rows 0-14
VSCPY:
        MOV A,M
        STAX D
        INX H
        INX D
        DCX B
        MOV A,B
        ORA C
        JNZ VSCPY
        LXI H,0FFC0H
        MVI B,40H
        MVI A,0A0H
VSCLR:
        MOV M,A
        INX H
        DCR B
        JNZ VSCLR
        LXI H,0FFC0H
        SHLD CURPTR
        RET

LISTST:
        MVI A,0FFH
        RET

;=============================================================================
; CP/M disk interface
;=============================================================================
HOME:
        MVI C,00H
SETTRK:
        MOV A,C
        STA CURTRK
        RET

SETSEC:
        MOV A,C
        STA CURSEC
        RET

SETDMA:
        MOV H,B
        MOV L,C
        SHLD DMAADR
        RET

SELDSK:
        MOV A,C
        CPI 02H
        JNC SELBAD
        STA CURDRV
        MVI A,0FFH
        STA DRVTRK
        MOV A,C
        ORA A
        LXI H,DPH0
        RZ
        LXI H,DPH1
        RET
SELBAD:
        LXI H,0000H
        RET

SECTRAN:
        MOV A,D
        ORA E
        JZ SXNONE
        XCHG
        DAD B
        MOV L,M
        MVI H,00H
        RET
SXNONE:
        MOV H,B
        MOV L,C
        INX H
        RET

;=============================================================================
; Native FDC+ Drive Type 8 / FD3712 service primitives
;=============================================================================
READ:
        CALL SELECT_SEEK
        JNZ IOERR
        MVI C,10
RDRETRY:
        MVI A,C_READ
        CALL DOCMD
        ANI S_NOTRDY+S_CRCERR
        JZ RDXFER
        CALL CLRERR
        DCR C
        JNZ RDRETRY
        JMP IOERR
RDXFER:
        LHLD DMAADR
        MVI C,80H
RDBLP:
        MVI A,C_RDBUF
        OUT CMDOUT
        IN DATAIN
        MOV M,A
        MVI A,C_SHIFT
        OUT CMDOUT
        INX H
        DCR C
        JNZ RDBLP
        XRA A
        OUT CMDOUT
        RET

WRITE:
        CALL SELECT_SEEK
        JNZ IOERR
        LHLD DMAADR
        MVI C,80H
WRBLP:
        MOV A,M
        OUT DATAOUT
        MVI A,C_WRTBUF
        OUT CMDOUT
        XRA A
        OUT CMDOUT
        INX H
        DCR C
        JNZ WRBLP
        MVI A,C_WRITE
        CALL DOCMD
        ANI S_NOTRDY+S_WRTPRT
        JZ IOSUCC
        CALL CLRERR
IOERR:
        MVI A,01H
        ORA A
        RET
IOSUCC:
        XRA A
        RET

SELECT_SEEK:
        XRA A
        OUT DATAOUT
        MVI A,C_LDCFG
        CALL OUTCMD
        CALL SELSEC
        CALL SEEK
        RET

SELSEC:
        LDA CURDRV
        ANI 03H
        RRCA
        RRCA
        MOV C,A
        LDA CURSEC
        ORA C
        OUT DATAOUT
        MVI A,C_DRVSEC
        CALL OUTCMD
        RET

SEEK:
        LDA CURTRK
        MOV C,A
        LDA DRVTRK
        CMP C
        RZ
        MOV A,C
        STA DRVTRK
        OUT DATAOUT
        MVI A,C_SETTRK
        CALL OUTCMD
        MVI A,C_SEEK
        CALL DOCMD
        ANI S_NOTRDY+S_CRCERR
        RZ
        CALL CLRERR
        MVI A,0FFH
        STA DRVTRK
        JMP FDCINIT

FDCINIT:
        XRA A
        STA CURDRV
        INR A
        STA CURSEC
        MVI A,C_RESET
        CALL OUTCMD
        CALL SELSEC
        MVI A,0FFH
        STA DRVTRK
        MVI A,C_RESTORE
        JMP DOCMD

DOCMD:
        CALL OUTCMD
DCWAIT:
        IN DATAIN
        ANI S_BUSY
        JNZ DCWAIT
        IN DATAIN
        RET

CLRERR:
        MVI A,C_CLRERR
OUTCMD:
        OUT CMDOUT
        XRA A
        OUT CMDOUT
        RET

; IBM 3740 6:1 skew
XLT:
        DB 1,7,13,19,25,5,11,17,23,3,9,15,21
        DB 2,8,14,20,26,6,12,18,24,4,10,16,22

DPH0:
        DW XLT,0,0,0,DIRBUF,DPB,CSV0,ALV0
DPH1:
        DW XLT,0,0,0,DIRBUF,DPB,CSV1,ALV1

; Standard IBM-3740 CP/M 2.2 DPB: 26x128, 77 tracks, 2 reserved tracks,
; 1K allocation blocks, 64 directory entries.
DPB:
        DW 26
        DB 3,7,0
        DW 242
        DW 63
        DB 0C0H,00H
        DW 16
        DW 2

BIOSEND:
        END
